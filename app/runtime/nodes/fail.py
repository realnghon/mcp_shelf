from app.runtime.state import AgentState


async def fail_node(state: AgentState) -> dict:
    """Handle failure case."""
    error = state.get("error") or "Max steps reached or unexpected error"
    return {"final_output": None, "error": error}
