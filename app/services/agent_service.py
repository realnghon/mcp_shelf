"""Agent service - orchestrates LangGraph runtime with session persistence."""

import asyncio
import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk

from app.runtime.adapters.models import get_chat_model
from app.runtime.nodes.build_tools import build_tools_node
from app.runtime.nodes.call_model import _lc_message_to_dict, _to_lc_messages
from app.runtime.nodes.execute_tool import execute_tool_node
from app.runtime.nodes.load_binding import load_binding_node
from app.runtime.state import AgentState
from app.schemas.runtime import RuntimeEvent
from app.schemas.session import MessageCreate, SessionCreate
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self):
        self.session_service = SessionService()
        self._running_sessions: dict[str, asyncio.Task] = {}

    async def create_session(self, data: SessionCreate, actor_id: str | None = None) -> dict:
        """Create a new session for multi-turn conversation."""
        return await self.session_service.create_session(data, actor_id)

    async def send_message(self, session_id: str, content: str) -> dict:
        """Add a user message to the session and return it."""
        msg = await self.session_service.add_message(
            session_id, MessageCreate(role="user", content=content)
        )
        return msg

    async def run_session(self, session_id: str) -> AsyncGenerator[RuntimeEvent, None]:
        """Run the LangGraph agent and yield SSE events.

        This is the core multi-turn conversation engine:
        1. Load session and binding config
        2. Load conversation history from DB
        3. Build initial state
        4. Execute graph
        5. Save results back to DB
        6. Stream events to client
        """
        session = await self.session_service.get_session(session_id)
        if not session:
            yield RuntimeEvent(event_type="error", data={"message": "Session not found"})
            return

        # Update session status
        await self.session_service.update_session_status(session_id, "running")

        try:
            # Load existing messages for multi-turn context
            db_messages = await self.session_service.list_messages(session_id)

            # Build initial state
            initial_state: AgentState = {
                "thread_id": session["thread_id"],
                "session_id": session_id,
                "binding_id": session.get("binding_id"),
                "model_key": session.get("model_key"),
                "messages": [
                    {
                        "role": m["role"],
                        "content": m["content"],
                        "tool_name": m.get("tool_name"),
                        "tool_call_id": m.get("tool_call_id"),
                        "tool_args": m.get("tool_args"),
                        "tool_result": m.get("tool_result"),
                    }
                    for m in db_messages
                ],
                "selected_capabilities": [],
                "available_tools": [],
                "max_steps": 8,
                "current_step": 0,
                "final_output": None,
                "error": None,
            }

            yield RuntimeEvent(event_type="start", data={"session_id": session_id})
            async for event in self._run_streaming_loop(session_id, initial_state):
                yield event

            await self.session_service.update_session_status(session_id, "idle")

        except Exception as e:
            logger.exception(f"Agent execution failed for session {session_id}")
            await self.session_service.update_session_status(session_id, "error", str(e))
            yield RuntimeEvent(event_type="error", data={"message": str(e)})

    async def stop_session(self, session_id: str) -> bool:
        """Stop a running session."""
        task = self._running_sessions.pop(session_id, None)
        if task and not task.done():
            task.cancel()
        await self.session_service.update_session_status(session_id, "idle")
        return True

    async def get_conversation(self, session_id: str) -> list[dict]:
        """Get all messages for a session (for multi-turn display)."""
        return await self.session_service.list_messages(session_id)

    async def _run_streaming_loop(
        self,
        session_id: str,
        initial_state: AgentState,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        state = dict(initial_state)
        state.update(await load_binding_node(state))
        state.update(await build_tools_node(state))

        while True:
            if state.get("error"):
                raise RuntimeError(state["error"])
            if state["current_step"] >= state["max_steps"]:
                raise RuntimeError("Max steps reached")

            state["current_step"] += 1
            model = await get_chat_model(
                binding_id=state.get("binding_id"),
                model_key_override=state.get("model_key"),
            )

            tools = state.get("available_tools", [])
            if tools:
                model = model.bind_tools(tools)

            lc_messages = _to_lc_messages(state.get("messages", []))
            merged_chunk: AIMessageChunk | None = None
            merged_message: AIMessage | None = None
            streamed_any = False

            async for chunk in model.astream(lc_messages):
                if isinstance(chunk, AIMessageChunk):
                    token = _extract_chunk_text(chunk)
                    if token:
                        streamed_any = True
                        yield RuntimeEvent(
                            event_type="token",
                            data={"content": token, "role": "assistant"},
                        )
                    merged_chunk = chunk if merged_chunk is None else merged_chunk + chunk
                    continue

                # Some providers return a full AIMessage in astream (no token chunks).
                if isinstance(chunk, AIMessage):
                    merged_message = chunk

            response_msg = merged_chunk or merged_message
            if response_msg is None:
                response_msg = await model.ainvoke(lc_messages)

            response_dict = _lc_message_to_dict(response_msg)
            state["messages"] = [*state.get("messages", []), response_dict]

            await self.session_service.add_message(
                session_id,
                MessageCreate(
                    role="assistant",
                    content=_stringify_content(response_dict.get("content")),
                ),
            )

            tool_calls = response_dict.get("tool_calls") or []
            if tool_calls:
                for tc in tool_calls:
                    yield RuntimeEvent(
                        event_type="tool_call",
                        data={
                            "tool_name": tc.get("name", ""),
                            "tool_args": tc.get("args", {}),
                            "tool_call_id": tc.get("id", ""),
                        },
                    )

                before_count = len(state["messages"])
                tool_output = await execute_tool_node(state)
                state.update(tool_output)
                new_tool_msgs = state["messages"][before_count:]

                for msg in new_tool_msgs:
                    yield RuntimeEvent(
                        event_type="tool_result",
                        data={
                            "tool_name": msg.get("tool_name", ""),
                            "tool_result": msg.get("tool_result", msg.get("content", "")),
                        },
                    )
                    await self.session_service.add_message(
                        session_id,
                        MessageCreate(
                            role="tool",
                            content=msg.get("content"),
                            tool_name=msg.get("tool_name"),
                            tool_call_id=msg.get("tool_call_id"),
                            tool_args=msg.get("tool_args"),
                            tool_result=msg.get("tool_result", msg.get("content")),
                        ),
                    )

                if state.get("error"):
                    raise RuntimeError(state["error"])
                continue

            content = _stringify_content(response_dict.get("content"))
            if not streamed_any and content:
                async for part in _chunk_text_stream(content):
                    yield RuntimeEvent(
                        event_type="token",
                        data={"content": part, "role": "assistant"},
                    )
            yield RuntimeEvent(event_type="done", data={"content": content})
            return


def _extract_chunk_text(chunk: AIMessageChunk) -> str:
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    # Fallback for provider-specific chunk payloads (OpenAI-compatible gateways).
    kw = getattr(chunk, "additional_kwargs", None)
    if isinstance(kw, dict):
        delta = kw.get("delta")
        if isinstance(delta, dict):
            text = delta.get("content")
            if isinstance(text, str):
                return text
        choices = kw.get("choices")
        if isinstance(choices, list):
            parts: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                d = choice.get("delta")
                if isinstance(d, dict):
                    text = d.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "".join(parts)
    return ""


def _stringify_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return "" if content is None else str(content)


async def _chunk_text_stream(content: str, chunk_size: int = 16) -> AsyncGenerator[str, None]:
    for i in range(0, len(content), chunk_size):
        yield content[i:i + chunk_size]
        await asyncio.sleep(0.01)
