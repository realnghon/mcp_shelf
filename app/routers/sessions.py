from fastapi import APIRouter, HTTPException, Query

from app.schemas.session import SessionCreate, MessageCreate, MessageOut
from app.schemas.common import PaginatedResponse
from app.services.session_service import SessionService

router = APIRouter()
svc = SessionService()


@router.get("", response_model=PaginatedResponse)
async def list_sessions(
    session_status: str | None = None,
    binding_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await svc.list_sessions(
        session_status=session_status, binding_id=binding_id,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_session(data: SessionCreate):
    return await svc.create_session(data)


@router.get("/{session_id}")
async def get_session(session_id: str):
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    ok = await svc.delete_session(session_id)
    if not ok:
        raise HTTPException(404, "Session not found")


@router.delete("", status_code=204)
async def delete_all_sessions():
    """Delete all sessions."""
    await svc.delete_all_sessions()


@router.get("/{session_id}/messages")
async def list_messages(session_id: str):
    return await svc.list_messages(session_id)


@router.post("/{session_id}/messages", status_code=201)
async def add_message(session_id: str, data: MessageCreate):
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return await svc.add_message(session_id, data)
