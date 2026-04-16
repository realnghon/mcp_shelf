"""Runtime router - agent execution with SSE streaming."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.services.agent_service import AgentService

router = APIRouter()
agent_svc = AgentService()


@router.post("/{session_id}/run")
async def run_session(session_id: str):
    """Trigger agent execution. Returns immediately; use /stream for SSE."""
    session = await agent_svc.session_service.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    # For non-streaming, we collect the result
    result_content = None
    async for event in agent_svc.run_session(session_id):
        if event.event_type == "done":
            result_content = event.data.get("content")
        elif event.event_type == "error":
            raise HTTPException(500, event.data.get("message", "Unknown error"))
    return {"session_id": session_id, "result": result_content}


@router.get("/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """SSE endpoint for streaming agent execution with multi-turn support."""

    async def event_generator():
        saw_token = False
        async for event in agent_svc.run_session(session_id):
            if await request.is_disconnected():
                break
            if event.event_type == "token":
                saw_token = True
                yield {
                    "event": event.event_type,
                    "data": json.dumps(event.data),
                }
                continue

            if event.event_type == "done" and not saw_token:
                content = event.data.get("content", "")
                if isinstance(content, str) and content:
                    for part in _chunk_text(content, 18):
                        if await request.is_disconnected():
                            break
                        yield {
                            "event": "token",
                            "data": json.dumps({"content": part, "role": "assistant"}),
                        }
                        await asyncio.sleep(0.01)

            yield {
                "event": event.event_type,
                "data": json.dumps(event.data),
            }

    return EventSourceResponse(
        event_generator(),
        ping=10,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


@router.post("/{session_id}/stop")
async def stop_session(session_id: str):
    ok = await agent_svc.stop_session(session_id)
    if not ok:
        raise HTTPException(400, "Could not stop session")
    return {"status": "stopped"}


@router.get("/{session_id}/trace")
async def get_trace(session_id: str):
    """Get the full conversation trace for a session."""
    messages = await agent_svc.get_conversation(session_id)
    return {"session_id": session_id, "messages": messages}
