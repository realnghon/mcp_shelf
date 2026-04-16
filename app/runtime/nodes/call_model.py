import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.runtime.adapters.models import get_chat_model
from app.runtime.state import AgentState


async def call_model_node(state: AgentState) -> dict:
    """Call the LLM with current messages and available tools."""
    messages = state.get("messages", [])
    tools = state.get("available_tools", [])

    # Increment step counter
    current_step = state.get("current_step", 0) + 1

    try:
        # Convert raw dicts to LangChain message objects
        lc_messages = _to_lc_messages(messages)

        # Get model
        model = await get_chat_model(
            binding_id=state.get("binding_id"),
            model_key_override=state.get("model_key"),
        )

        # Bind tools if available
        if tools:
            model = model.bind_tools(tools)

        # Call model
        response = await model.ainvoke(lc_messages)

        # Convert response back to dict
        new_messages = list(messages)  # copy existing
        response_dict = _lc_message_to_dict(response)
        new_messages.append(response_dict)

        return {
            "messages": new_messages,
            "current_step": current_step,
        }

    except Exception as e:
        return {
            "messages": messages,
            "current_step": current_step,
            "error": _normalize_model_error(str(e)),
        }


def _to_lc_messages(msg_dicts: list[dict]) -> list:
    """Convert raw message dicts to LangChain message objects."""
    result = []
    for m in msg_dicts:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            ai_msg = AIMessage(content=content)
            if m.get("tool_calls"):
                ai_msg.tool_calls = _normalize_tool_calls(m["tool_calls"])
            result.append(ai_msg)
        elif role == "tool":
            tool_content = m.get("content")
            if tool_content is None:
                tool_content = m.get("tool_result", "")
            result.append(ToolMessage(
                content=tool_content,
                tool_call_id=m.get("tool_call_id", ""),
                name=m.get("tool_name"),
            ))
        elif role == "system":
            result.append(SystemMessage(content=content))
    return result


def _lc_message_to_dict(msg) -> dict:
    """Convert LangChain message to raw dict."""
    if isinstance(msg, AIMessage):
        result = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = _normalize_tool_calls(msg.tool_calls)
        return result
    elif isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, ToolMessage):
        return {"role": "tool", "content": msg.content, "tool_call_id": msg.tool_call_id}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    return {"role": "unknown", "content": str(msg)}


def _normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    """Normalize tool call payload across providers and SDK shapes."""
    if not isinstance(tool_calls, list):
        return []

    normalized: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = call.get("name") or call.get("function", {}).get("name")
        raw_args = call.get("args")
        if raw_args is None:
            raw_args = call.get("function", {}).get("arguments", {})
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except json.JSONDecodeError:
                raw_args = {"input": raw_args}
        if not isinstance(raw_args, dict):
            raw_args = {"input": raw_args}
        normalized.append(
            {
                "id": call.get("id", ""),
                "name": name or "",
                "args": raw_args,
            }
        )
    return normalized


def _normalize_model_error(raw_error: str) -> str:
    if "'str' object has no attribute 'model_dump'" in raw_error:
        return (
            "LLM endpoint returned a non-OpenAI response body. "
            "For OpenAI-compatible providers, set base_url to include '/v1' "
            "(example: https://your-endpoint/v1)."
        )
    return raw_error
