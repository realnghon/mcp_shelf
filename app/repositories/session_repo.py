import json
from typing import Any

import aiosqlite

from app.core.db import get_db
from app.core.config import settings
from app.schemas.common import new_id, utcnow


class SessionRepo:
    async def list_all(
        self,
        session_status: str | None = None,
        binding_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        db = await get_db()
        conditions = []
        params: list[Any] = []

        if session_status:
            conditions.append("session_status = ?")
            params.append(session_status)
        if binding_id:
            conditions.append("binding_id = ?")
            params.append(binding_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_sql = f"SELECT COUNT(*) FROM runtime_sessions {where}"
        data_sql = f"SELECT * FROM runtime_sessions {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"

        cursor = await db.execute(count_sql, params)
        count_row = await cursor.fetchone()
        total = int(count_row[0]) if count_row else 0
        cursor = await db.execute(data_sql, params + [page_size, (page - 1) * page_size])
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["runtime_config"] = json.loads(d["runtime_config"]) if isinstance(d["runtime_config"], str) else d["runtime_config"]
            results.append(d)
        return results, total

    async def get_by_id(self, session_id: str) -> dict | None:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM runtime_sessions WHERE id = ?", [session_id])
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["runtime_config"] = json.loads(d["runtime_config"]) if isinstance(d["runtime_config"], str) else d["runtime_config"]
        return d

    async def get_by_thread_id(self, thread_id: str) -> dict | None:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM runtime_sessions WHERE thread_id = ?", [thread_id])
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["runtime_config"] = json.loads(d["runtime_config"]) if isinstance(d["runtime_config"], str) else d["runtime_config"]
        return d

    async def create(self, data: dict[str, Any]) -> dict:
        db = await get_db()
        now = utcnow()
        import uuid
        thread_id = uuid.uuid4().hex
        record = {
            "id": new_id(),
            "thread_id": thread_id,
            "binding_id": data.get("binding_id"),
            "title": data.get("title"),
            "actor_id": data.get("actor_id"),
            "session_status": "idle",
            "model_key": data.get("model_key") or f"openai:{settings.openai_model}",
            "runtime_config": json.dumps(data.get("runtime_config", {})),
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO runtime_sessions ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        record["runtime_config"] = data.get("runtime_config", {})
        return record

    async def update(self, session_id: str, data: dict[str, Any]) -> dict | None:
        db = await get_db()
        existing = await self.get_by_id(session_id)
        if not existing:
            return None

        sets = []
        params: list[Any] = []
        for key, val in data.items():
            if val is None and key not in ("binding_id", "title", "last_error"):
                continue
            if key == "runtime_config":
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)

        if not sets:
            return existing

        sets.append("updated_at = ?")
        params.append(utcnow())
        params.append(session_id)
        await db.execute(f"UPDATE runtime_sessions SET {', '.join(sets)} WHERE id = ?", params)
        await db.commit()
        return await self.get_by_id(session_id)

    async def delete(self, session_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute("DELETE FROM runtime_sessions WHERE id = ?", [session_id])
        await db.commit()
        return cursor.rowcount > 0

    async def delete_all(self) -> int:
        """Delete all sessions and their messages. Returns count of sessions deleted."""
        db = await get_db()
        # Delete messages first (foreign key)
        await db.execute("DELETE FROM runtime_messages")
        cursor = await db.execute("DELETE FROM runtime_sessions")
        await db.commit()
        return cursor.rowcount


class MessageRepo:
    async def list_by_session(self, session_id: str) -> list[dict]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM runtime_messages WHERE session_id = ? ORDER BY message_index ASC",
            [session_id],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def add(self, session_id: str, data: dict[str, Any]) -> dict:
        db = await get_db()
        now = utcnow()
        # Get next index
        cursor = await db.execute(
            "SELECT COALESCE(MAX(message_index), -1) FROM runtime_messages WHERE session_id = ?",
            [session_id],
        )
        max_row = await cursor.fetchone()
        max_idx = int(max_row[0]) if max_row else -1
        next_idx = max_idx + 1

        record = {
            "id": new_id(),
            "session_id": session_id,
            "role": data["role"],
            "content": data.get("content"),
            "tool_event_type": data.get("tool_event_type") or "result",
            "tool_name": data.get("tool_name"),
            "tool_call_id": data.get("tool_call_id"),
            "tool_args": json.dumps(data["tool_args"]) if isinstance(data.get("tool_args"), (dict, list)) else data.get("tool_args"),
            "tool_result": json.dumps(data["tool_result"]) if isinstance(data.get("tool_result"), (dict, list)) else data.get("tool_result"),
            "message_index": next_idx,
            "created_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO runtime_messages ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        return record

    async def delete(self, session_id: str, message_id: str) -> bool:
        db = await get_db()
        current = await self.get_by_id(session_id, message_id)
        if not current:
            return False

        if current.get("role") == "user":
            cursor = await db.execute(
                "DELETE FROM runtime_messages WHERE session_id = ? AND message_index >= ?",
                [session_id, int(current["message_index"])],
            )
        else:
            cursor = await db.execute(
                "DELETE FROM runtime_messages WHERE session_id = ? AND id = ?",
                [session_id, message_id],
            )
        await db.commit()
        return cursor.rowcount > 0

    async def get_by_id(self, session_id: str, message_id: str) -> dict | None:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM runtime_messages WHERE session_id = ? AND id = ?",
            [session_id, message_id],
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def edit_user_message_and_truncate_following(
        self,
        session_id: str,
        message_id: str,
        content: str,
    ) -> tuple[dict | None, int]:
        db = await get_db()
        current = await self.get_by_id(session_id, message_id)
        if not current:
            return None, 0
        if current.get("role") != "user":
            raise ValueError("Only user messages can be edited")

        await db.execute(
            "UPDATE runtime_messages SET content = ? WHERE session_id = ? AND id = ?",
            [content, session_id, message_id],
        )
        cursor = await db.execute(
            "DELETE FROM runtime_messages WHERE session_id = ? AND message_index > ?",
            [session_id, int(current["message_index"])],
        )
        await db.commit()

        updated = await self.get_by_id(session_id, message_id)
        return updated, int(cursor.rowcount or 0)
