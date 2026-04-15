from app.runtime.state import AgentState


async def execute_tool_node(state: AgentState) -> dict:
    """Execute tool calls from the last assistant message."""
    messages = state.get("messages", [])
    tools = state.get("available_tools", [])

    if not messages:
        return {"error": "No messages to process"}

    last_msg = messages[-1]
    tool_calls = last_msg.get("tool_calls", [])

    if not tool_calls:
        return {}

    # Build tool lookup
    tool_map = {}
    for t in tools:
        name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
        if name:
            tool_map[name] = t

    new_messages = list(messages)
    errors = []

    for tc in tool_calls:
        tool_name = tc.get("name", tc.get("function", {}).get("name", ""))
        tool_args = tc.get("args", tc.get("function", {}).get("arguments", {}))
        tool_call_id = tc.get("id", "")

        tool = tool_map.get(tool_name)

        if not tool:
            new_messages.append({
                "role": "tool",
                "content": f"Tool '{tool_name}' not found",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_result": f"Error: Tool '{tool_name}' not found",
            })
            errors.append(f"Tool '{tool_name}' not found")
            continue

        try:
            if hasattr(tool, "coroutine") and tool.coroutine:
                result = await tool.coroutine(**tool_args)
            elif hasattr(tool, "func"):
                result = tool.func(**tool_args)
            elif hasattr(tool, "ainvoke"):
                result = await tool.ainvoke(tool_args)
            elif hasattr(tool, "invoke"):
                result = tool.invoke(tool_args)
            else:
                result = f"Error: Cannot execute tool '{tool_name}'"

            result_str = str(result) if result is not None else ""

            new_messages.append({
                "role": "tool",
                "content": result_str,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_args": str(tool_args),
                "tool_result": result_str,
            })

        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {e}"
            new_messages.append({
                "role": "tool",
                "content": error_msg,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_result": error_msg,
            })
            errors.append(error_msg)

    return {
        "messages": new_messages,
        "error": "; ".join(errors) if errors else None,
    }
