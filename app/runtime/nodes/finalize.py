from app.runtime.state import AgentState


async def finalize_node(state: AgentState) -> dict:
    """Extract final answer from the conversation."""
    messages = state.get("messages", [])

    final_output = None
    # Look for the last assistant message with content
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            final_output = msg["content"]
            break

    return {"final_output": final_output, "error": None}
