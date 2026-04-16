from __future__ import annotations

from typing import Any

from app.repositories.capability_repo import CapabilityRepo
from app.runtime.adapters.local_tools import get_capability_tools, get_local_tools
from app.runtime.adapters.mcp import get_mcp_tools
from app.runtime.adapters.skills import get_skill_tools
from app.runtime.state import AgentState


async def build_tools_node(state: AgentState) -> dict:
    """Build tool list from selected capabilities.

    Mount strategy:
    - Always-on local tools
    - mounted `tool` capabilities
    - mounted `skill` capabilities
    - mounted `mcp` capabilities
    """
    tools = []
    cap_repo = CapabilityRepo()

    # Always include local tools (baseline toolbelt).
    tools.extend(get_local_tools())

    for cap_ref in state.get("selected_capabilities", []):
        cap = await cap_repo.get_by_id(cap_ref["capability_id"])
        if not cap or cap["status"] != "active":
            continue

        runtime_overrides = cap_ref.get("runtime_overrides") or {}
        config = _merge_config(cap.get("connection_config", {}), runtime_overrides)

        try:
            if cap_ref["kind"] == "mcp":
                tools.extend(await get_mcp_tools(config))
            elif cap_ref["kind"] == "tool":
                tools.extend(get_capability_tools(cap, config))
            elif cap_ref["kind"] == "skill":
                tools.extend(await get_skill_tools(cap, config))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load capability tools for %s (%s): %s",
                cap.get("slug"),
                cap_ref.get("kind"),
                e,
            )

    return {"available_tools": _dedupe_tools(tools)}


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


def _dedupe_tools(tools: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result = []
    for tool in tools:
        name = getattr(tool, "name", None)
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(tool)
    return result
