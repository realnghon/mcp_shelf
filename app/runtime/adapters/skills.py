"""Skill adapter - placeholder for future skill loading."""

from langchain_core.tools import StructuredTool


async def get_skill_tools(capability_config: dict) -> list[StructuredTool]:
    """Load tools from a skill definition.

    Skills are more complex than tools - they may include
    multi-step workflows, prompt templates, etc.
    For now, this is a placeholder.
    """
    return []
