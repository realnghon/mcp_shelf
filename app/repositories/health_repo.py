from __future__ import annotations

from typing import Any

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


class HealthRepo:
    async def create(
        self,
        capability_id: str,
        status: str,
        latency_ms: int | None = None,
        detail: str | None = None,
        discovery_status: str | None = None,
    ) -> dict:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "capability_id": capability_id,
            "status": status,
            "latency_ms": latency_ms,
            "detail": detail,
            "discovery_status": discovery_status,
            "checked_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO health_checks ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        return record

    async def ensure_discovery_status_column(self) -> None:
        db = await get_db()
        cursor = await db.execute("PRAGMA table_info(health_checks)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "discovery_status" not in columns:
            await db.execute("ALTER TABLE health_checks ADD COLUMN discovery_status TEXT")
            await db.commit()

    async def list_for_capability(self, capability_id: str, limit: int = 10) -> list[dict]:
        await self.ensure_discovery_status_column()
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM health_checks WHERE capability_id = ? ORDER BY checked_at DESC LIMIT ?",
            [capability_id, limit],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_summary(self) -> list[dict[str, Any]]:
        await self.ensure_discovery_status_column()
        db = await get_db()
        cursor = await db.execute(
            """
            SELECT c.id, c.name, c.kind, c.status as cap_status,
                   hc.status as health_status, hc.latency_ms, hc.checked_at, hc.discovery_status
            FROM capabilities c
            LEFT JOIN health_checks hc ON c.id = hc.capability_id
            AND hc.checked_at = (SELECT MAX(checked_at) FROM health_checks WHERE capability_id = c.id)
            ORDER BY c.name
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
