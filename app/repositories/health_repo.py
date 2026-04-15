from typing import Any

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


class HealthRepo:
    async def create(self, capability_id: str, status: str,
                     latency_ms: int | None = None, detail: str | None = None) -> dict:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "capability_id": capability_id,
            "status": status,
            "latency_ms": latency_ms,
            "detail": detail,
            "checked_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO health_checks ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        return record

    async def list_for_capability(self, capability_id: str, limit: int = 10) -> list[dict]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM health_checks WHERE capability_id = ? ORDER BY checked_at DESC LIMIT ?",
            [capability_id, limit],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_summary(self) -> list[dict[str, Any]]:
        db = await get_db()
        cursor = await db.execute("""
            SELECT c.id, c.name, c.kind, c.status as cap_status,
                   hc.status as health_status, hc.latency_ms, hc.checked_at
            FROM capabilities c
            LEFT JOIN health_checks hc ON c.id = hc.capability_id
            AND hc.checked_at = (SELECT MAX(checked_at) FROM health_checks WHERE capability_id = c.id)
            ORDER BY c.name
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
