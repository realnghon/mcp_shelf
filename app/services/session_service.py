from typing import Any

from app.repositories.session_repo import SessionRepo, MessageRepo
from app.repositories.audit_repo import AuditRepo
from app.schemas.session import SessionCreate, MessageCreate


class SessionService:
    def __init__(self):
        self.session_repo = SessionRepo()
        self.message_repo = MessageRepo()
        self.audit = AuditRepo()

    async def list_sessions(self, **kwargs) -> tuple[list[dict], int]:
        return await self.session_repo.list_all(**kwargs)

    async def get_session(self, session_id: str) -> dict | None:
        return await self.session_repo.get_by_id(session_id)

    async def create_session(self, data: SessionCreate, actor_id: str | None = None) -> dict:
        record = await self.session_repo.create(data.model_dump())
        await self.audit.log("create", "session", record["id"], actor_id)
        return record

    async def update_session_status(self, session_id: str, status: str,
                                     last_error: str | None = None) -> dict | None:
        update_data: dict[str, Any] = {"session_status": status}
        if last_error is not None:
            update_data["last_error"] = last_error
        return await self.session_repo.update(session_id, update_data)

    async def delete_session(self, session_id: str, actor_id: str | None = None) -> bool:
        ok = await self.session_repo.delete(session_id)
        if ok:
            await self.audit.log("delete", "session", session_id, actor_id)
        return ok

    # --- Messages ---

    async def list_messages(self, session_id: str) -> list[dict]:
        return await self.message_repo.list_by_session(session_id)

    async def add_message(self, session_id: str, data: MessageCreate) -> dict:
        return await self.message_repo.add(session_id, data.model_dump())

    async def add_messages_batch(self, session_id: str, messages: list[dict]) -> list[dict]:
        results = []
        for msg in messages:
            record = await self.message_repo.add(session_id, msg)
            results.append(record)
        return results
