"""Agent service - orchestrates LangGraph runtime with session persistence."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.runtime.graph import build_graph
from app.runtime.state import AgentState
from app.services.session_service import SessionService
from app.schemas.session import SessionCreate, MessageCreate
from app.schemas.runtime import RuntimeEvent

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

            # Build and run the graph
            graph = build_graph()

            yield RuntimeEvent(event_type="start", data={"session_id": session_id})

            # Stream graph execution
            final_state = None
            async for event in graph.astream(initial_state):
                # Each event is a dict with node name as key
                for node_name, node_output in event.items():
                    # Check for new messages
                    if "messages" in node_output:
                        new_msgs = node_output["messages"]
                        # Find messages that weren't in our initial set
                        existing_count = len(initial_state["messages"])
                        for msg in new_msgs[existing_count:]:
                            # Save to DB
                            role = msg.get("role", "assistant")
                            if role == "assistant":
                                yield RuntimeEvent(
                                    event_type="token",
                                    data={"content": msg.get("content", ""), "role": "assistant"},
                                )
                                # Check for tool calls
                                if msg.get("tool_calls"):
                                    for tc in msg["tool_calls"]:
                                        yield RuntimeEvent(
                                            event_type="tool_call",
                                            data={
                                                "tool_name": tc.get("name", ""),
                                                "tool_args": tc.get("args", {}),
                                                "tool_call_id": tc.get("id", ""),
                                            },
                                        )

                                await self.session_service.add_message(
                                    session_id,
                                    MessageCreate(
                                        role="assistant",
                                        content=msg.get("content"),
                                        tool_name=None,
                                        tool_call_id=None,
                                    ),
                                )
                            elif role == "tool":
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

                    # Check for errors
                    if node_output.get("error"):
                        yield RuntimeEvent(
                            event_type="error",
                            data={"message": node_output["error"]},
                        )

                    final_state = node_output

            # Determine final status
            if final_state and final_state.get("final_output"):
                yield RuntimeEvent(
                    event_type="done",
                    data={"content": final_state["final_output"]},
                )
                await self.session_service.update_session_status(session_id, "idle")
            elif final_state and final_state.get("error"):
                await self.session_service.update_session_status(
                    session_id, "error", final_state["error"]
                )
            else:
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
