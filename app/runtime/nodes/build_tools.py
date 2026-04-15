from app.runtime.state import AgentState
from app.runtime.adapters.local_tools import get_local_tools
from app.runtime.adapters.mcp import get_mcp_tools
from app.repositories.capability_repo import CapabilityRepo


async def build_tools_node(state: AgentState) -> dict:
    """Build tool list from selected capabilities."""
    tools = []
    cap_repo = CapabilityRepo()

    # Always include local tools
    local_tools = get_local_tools()
    tools.extend(local_tools)

    # Load MCP tools for MCP capabilities
    for cap_ref in state.get("selected_capabilities", []):
        if cap_ref["kind"] == "mcp":
            cap = await cap_repo.get_by_id(cap_ref["capability_id"])
            if cap and cap["status"] == "active":
                try:
                    mcp_tools = await get_mcp_tools(cap["connection_config"])
                    tools.extend(mcp_tools)
                except Exception as e:
                    # Non-fatal: just skip this capability's tools
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to load MCP tools for {cap['slug']}: {e}"
                    )

    return {"available_tools": tools}
