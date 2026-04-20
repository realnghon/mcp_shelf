from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from app.repositories.capability_repo import CapabilityRepo


MountType = Literal["tool", "mcp", "prompt"]


class ResolvedCapability(TypedDict):
    capability: dict[str, Any]
    config: dict[str, Any]
    mount_type: MountType
    prompt_fragment: str | None


async def resolve_selected_capabilities(
    selected_capabilities: list[dict[str, Any]],
) -> list[ResolvedCapability]:
    """Resolve capability refs into runtime-ready mount descriptors."""
    repo = CapabilityRepo()
    resolved: list[ResolvedCapability] = []
    for cap_ref in selected_capabilities:
        cap = await repo.get_by_id(cap_ref["capability_id"])
        if not cap or cap.get("status") != "active":
            continue

        runtime_overrides = cap_ref.get("runtime_overrides") or {}
        config = _merge_config(cap.get("connection_config", {}), runtime_overrides)
        mount_type = _resolve_mount_type(cap_ref, cap)

        resolved.append(
            {
                "capability": cap,
                "config": config,
                "mount_type": mount_type,
                "prompt_fragment": _extract_prompt_fragment(cap, config) if mount_type == "prompt" else None,
            }
        )
    return resolved


def _resolve_mount_type(cap_ref: dict[str, Any], cap: dict[str, Any]) -> MountType:
    cap_kind = (cap_ref.get("kind") or cap.get("kind") or "").lower()
    cap_type = (cap.get("type") or "").lower()
    source_type = (cap.get("source_type") or "").lower()

    if cap_kind == "skill" or cap_type in {"prompt", "workflow"}:
        return "prompt"
    if source_type == "mcp_server" or cap_kind == "mcp":
        return "mcp"
    return "tool"


def _merge_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    merged.update(overrides or {})
    return _render_template_values(merged, overrides or {})


def _render_template_values(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _render_template_values(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template_values(item, variables) for item in value]
    if isinstance(value, str):
        rendered = value
        for key, val in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(val))
        return rendered
    return value


def _extract_prompt_fragment(cap: dict[str, Any], config: dict[str, Any]) -> str | None:
    prompt = (
        config.get("prompt")
        or config.get("system_prompt")
        or config.get("instructions")
        or config.get("instruction")
    )
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()

    raw_path = config.get("path")
    if isinstance(raw_path, str) and raw_path.strip():
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            if path.is_dir():
                entry_file = str(config.get("entry_file") or "SKILL.md").strip() or "SKILL.md"
                entry_path = path / entry_file
                if entry_path.exists():
                    return _compose_skill_fragment(
                        primary_path=entry_path,
                        include_files=config.get("include_files"),
                        base_dir=path,
                    )
                fallback = path / "SKILL.md"
                if fallback.exists():
                    return _compose_skill_fragment(
                        primary_path=fallback,
                        include_files=config.get("include_files"),
                        base_dir=path,
                    )
            elif path.exists():
                return _compose_skill_fragment(
                    primary_path=path,
                    include_files=config.get("include_files"),
                    base_dir=path.parent,
                )
        except Exception:
            return None

    metadata = cap.get("metadata")
    if isinstance(metadata, dict):
        metadata_prompt = metadata.get("prompt")
        if isinstance(metadata_prompt, str) and metadata_prompt.strip():
            return metadata_prompt.strip()
    return None


def _compose_skill_fragment(
    primary_path: Path,
    include_files: Any,
    base_dir: Path,
) -> str:
    fragments: list[str] = []
    primary_text = primary_path.read_text(encoding="utf-8").strip()
    if primary_text:
        fragments.append(primary_text)

    if isinstance(include_files, list):
        for raw in include_files:
            rel = str(raw or "").strip()
            if not rel:
                continue
            include_path = base_dir / rel
            try:
                if include_path.exists() and include_path.is_file():
                    included = include_path.read_text(encoding="utf-8").strip()
                    if included:
                        fragments.append(f"\n\n# Included: {rel}\n{included}")
            except Exception:
                continue

    return "\n".join(fragments).strip()
