"""Skill adapter - mounts local skill files as callable guidance tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class SkillInput(BaseModel):
    objective: str = Field(description="What you want the skill to accomplish in this turn")


def _read_skill_text(path: Path) -> str:
    if not path.exists():
        return f"Skill file not found: {path}"
    return path.read_text(encoding="utf-8")


def _resolve_skill_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


async def get_skill_tools(
    capability: dict[str, Any],
    config: dict[str, Any],
) -> list[StructuredTool]:
    """Load a `skill` capability as a callable skill-guide tool.

    Supported config keys:
    - path: local path to SKILL.md
    - tool_name: override exported tool name
    """
    raw_path = (config or {}).get("path")
    if not raw_path:
        return []

    skill_path = _resolve_skill_path(raw_path)
    tool_name = (config or {}).get("tool_name") or f"skill_{capability.get('slug', 'unknown')}"
    description = capability.get("description") or f"Skill guidance loaded from {skill_path}"
    skill_text = _read_skill_text(skill_path)

    async def _run_skill(objective: str) -> str:
        return (
            f"Skill objective: {objective}\n\n"
            f"Skill source: {skill_path}\n\n"
            f"{skill_text}"
        )

    return [
        StructuredTool.from_function(
            coroutine=_run_skill,
            name=tool_name,
            description=description,
            args_schema=SkillInput,
        )
    ]
