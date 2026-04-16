from __future__ import annotations

import json
from typing import Any

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


class CapabilityTestRepo:
    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "capability_id": data["capability_id"],
            "status": data["status"],
            "latency_ms": data.get("latency_ms"),
            "request_payload": json.dumps(data.get("request_payload", {})),
            "response_payload": json.dumps(data.get("response_payload", {})),
            "error_message": data.get("error_message"),
            "tested_at": data.get("tested_at", now),
            "created_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(
            f"INSERT INTO capability_tests ({cols}) VALUES ({placeholders})",
            list(record.values()),
        )
        await db.commit()
        return self._row_to_dict(record)

    async def list_for_capability(self, capability_id: str, limit: int = 10) -> list[dict[str, Any]]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM capability_tests WHERE capability_id = ? ORDER BY tested_at DESC LIMIT ?",
            [capability_id, limit],
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(dict(row)) for row in rows]

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for key in ("request_payload", "response_payload"):
            if isinstance(result.get(key), str):
                result[key] = json.loads(result[key])
        return result
