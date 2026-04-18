import json
import logging

from app.runtime.state import AgentState

logger = logging.getLogger(__name__)


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
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except json.JSONDecodeError:
                tool_args = {"input": tool_args}
        if not isinstance(tool_args, dict):
            tool_args = {"input": tool_args}

        tool = tool_map.get(tool_name)

        if not tool:
            logger.warning("tool_not_found name=%s tool_call_id=%s", tool_name, tool_call_id)
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
            logger.info("tool_call_start name=%s tool_call_id=%s", tool_name, tool_call_id)
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
            logger.info(
                "tool_call_done name=%s tool_call_id=%s result_preview=%s",
                tool_name,
                tool_call_id,
                result_str[:220],
            )

            new_messages.append({
                "role": "tool",
                "content": result_str,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_args": str(tool_args),
                "tool_result": result_str,
            })

        except Exception as e:
            logger.exception("tool_call_failed name=%s tool_call_id=%s", tool_name, tool_call_id)
            error_msg = f"Error executing tool '{tool_name}': {e}"
            new_messages.append({
                "role": "tool",
                "content": error_msg,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_result": error_msg,
            })
            errors.append(error_msg)

    if errors:
        logger.warning("tool_call_nonfatal_errors count=%s", len(errors))

    return {
        "messages": new_messages,
        # Tool-level failures are surfaced as tool messages and should not hard-stop
        # the whole run; the model can inspect the error and retry with corrected args.
        "error": None,
    }
