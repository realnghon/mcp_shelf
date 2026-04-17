from __future__ import annotations

from typing import Any

from app.runtime.assembly.capability_resolver import resolve_selected_capabilities
from app.runtime.assembly.preset_assembler import assemble_messages
from app.runtime.adapters.local_tools import get_capability_tools, get_local_tools
from app.runtime.adapters.mcp import get_mcp_tools
from app.runtime.state import AgentState


async def build_tools_node(state: AgentState) -> dict:
    """Build tool list from selected capabilities.

    Mount strategy (phase2):
    - Always-on local tools
    - tool-like capabilities resolved by source_type (builtin/plugin/custom/mcp_server)
    - prompt/workflow/skill capabilities are injected into system prompt guidance
    """
    tools = []
    prompt_fragments: list[str] = []

    # Always include local tools (baseline toolbelt).
    tools.extend(get_local_tools())

    resolved = await resolve_selected_capabilities(state.get("selected_capabilities", []))
    for item in resolved:
        cap = item["capability"]
        config = item["config"]

        try:
            if item["mount_type"] == "prompt":
                if item["prompt_fragment"]:
                    prompt_fragments.append(item["prompt_fragment"])
                continue

            if item["mount_type"] == "mcp":
                tools.extend(await get_mcp_tools(config))
            else:
                tools.extend(get_capability_tools(cap, config))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load capability tools for %s (%s): %s",
                cap.get("slug"),
                cap.get("kind"),
                e,
            )

    result: dict[str, Any] = {"available_tools": _dedupe_tools(tools)}
    if prompt_fragments:
        result["messages"] = assemble_messages(
            messages=state.get("messages", []),
            prompt_fragments=prompt_fragments,
        )
    return result


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
