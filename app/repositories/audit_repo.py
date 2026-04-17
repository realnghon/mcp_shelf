import json
from typing import Any

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


class AuditRepo:
    async def log(self, action: str, target_type: str, target_id: str | None = None,
                  actor_id: str | None = None, payload: dict | None = None) -> dict:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": json.dumps(payload or {}),
            "created_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO audit_logs ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        record["payload"] = payload or {}
        return record

    async def list_all(
        self,
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        db = await get_db()
        conditions = []
        params: list[Any] = []

        if action:
            conditions.append("action = ?")
            params.append(action)
        if target_type:
            conditions.append("target_type = ?")
            params.append(target_type)
        if target_id:
            conditions.append("target_id = ?")
            params.append(target_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_sql = f"SELECT COUNT(*) FROM audit_logs {where}"
        data_sql = f"SELECT * FROM audit_logs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"

        cursor = await db.execute(count_sql, params)
        count_row = await cursor.fetchone()
        total = int(count_row[0]) if count_row else 0
        cursor = await db.execute(data_sql, params + [page_size, (page - 1) * page_size])
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"]) if isinstance(d["payload"], str) else d["payload"]
            results.append(d)
        return results, total
