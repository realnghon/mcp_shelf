import json
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from app.runtime.state import AgentState
from app.runtime.adapters.models import get_chat_model


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
        model = await get_chat_model(state.get("binding_id"))

        # Bind tools if available
        if tools:
            # Convert to LangChain tool format
            lc_tools = _convert_tools(tools)
            model = model.bind_tools(lc_tools) if lc_tools else model

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
            "error": str(e),
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
                ai_msg.tool_calls = m["tool_calls"]
            result.append(ai_msg)
        elif role == "tool":
            result.append(ToolMessage(
                content=m.get("tool_result", ""),
                tool_call_id=m.get("tool_call_id", ""),
            ))
        elif role == "system":
            result.append(SystemMessage(content=content))
    return result


def _lc_message_to_dict(msg) -> dict:
    """Convert LangChain message to raw dict."""
    if isinstance(msg, AIMessage):
        result = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = msg.tool_calls
        return result
    elif isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, ToolMessage):
        return {"role": "tool", "content": msg.content, "tool_call_id": msg.tool_call_id}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    return {"role": "unknown", "content": str(msg)}


def _convert_tools(tools: list) -> list:
    """Convert tool dicts/objects to LangChain tool format."""
    lc_tools = []
    for t in tools:
        if hasattr(t, "name"):
            # Already a LangChain tool
            lc_tools.append(t)
        elif isinstance(t, dict):
            # Raw tool definition - convert to structured tool
            from langchain_core.tools import StructuredTool
            lc_tools.append(StructuredTool(
                name=t.get("name", "unknown"),
                description=t.get("description", ""),
                func=lambda **kwargs: kwargs,
                coroutine=lambda **kwargs: kwargs,
                args_schema=t.get("args_schema"),
            ))
    return lc_tools
