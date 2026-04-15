import json
from typing import Any

import aiosqlite

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    # Parse JSON columns
    for key in ("tags", "config_schema", "connection_config", "metadata"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    return d


class CapabilityRepo:
    async def list_all(
        self,
        kind: str | None = None,
        status: str | None = None,
        category: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        db = await get_db()
        conditions = []
        params: list[Any] = []

        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if search:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend(["%" + search + "%", "%" + search + "%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_sql = f"SELECT COUNT(*) FROM capabilities {where}"
        data_sql = f"SELECT * FROM capabilities {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"

        cursor = await db.execute(count_sql, params)
        total = (await cursor.fetchone())[0]
        cursor = await db.execute(data_sql, params + [page_size, (page - 1) * page_size])
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows], total

    async def get_by_id(self, cap_id: str) -> dict | None:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM capabilities WHERE id = ?", [cap_id])
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    async def get_by_slug(self, slug: str) -> dict | None:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM capabilities WHERE slug = ?", [slug])
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    async def create(self, data: dict[str, Any]) -> dict:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "kind": data["kind"],
            "name": data["name"],
            "slug": data["slug"],
            "description": data.get("description"),
            "category": data.get("category"),
            "tags": json.dumps(data.get("tags", [])),
            "version": data.get("version", "0.1.0"),
            "visibility": data.get("visibility", "public"),
            "status": "active",
            "owner_id": data.get("owner_id"),
            "config_schema": json.dumps(data.get("config_schema", {})),
            "connection_config": json.dumps(data.get("connection_config", {})),
            "metadata": json.dumps(data.get("metadata", {})),
            "created_at": now,
            "updated_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO capabilities ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        return _row_to_dict(record)

    async def update(self, cap_id: str, data: dict[str, Any]) -> dict | None:
        db = await get_db()
        existing = await self.get_by_id(cap_id)
        if not existing:
            return None

        sets = []
        params: list[Any] = []
        for key, val in data.items():
            if val is None and key not in ("description", "category", "owner_id"):
                continue
            if key in ("tags", "config_schema", "connection_config", "metadata"):
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)

        if not sets:
            return existing

        sets.append("updated_at = ?")
        params.append(utcnow())
        params.append(cap_id)
        await db.execute(f"UPDATE capabilities SET {', '.join(sets)} WHERE id = ?", params)
        await db.commit()
        return await self.get_by_id(cap_id)

    async def delete(self, cap_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute("DELETE FROM capabilities WHERE id = ?", [cap_id])
        await db.commit()
        return cursor.rowcount > 0

    async def set_status(self, cap_id: str, status: str) -> dict | None:
        return await self.update(cap_id, {"status": status, "updated_at": utcnow()})

    # --- Versions ---

    async def list_versions(self, cap_id: str) -> list[dict]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM capability_versions WHERE capability_id = ? ORDER BY created_at DESC",
            [cap_id],
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["snapshot"] = json.loads(d["snapshot"]) if isinstance(d["snapshot"], str) else d["snapshot"]
            results.append(d)
        return results

    async def create_version(self, cap_id: str, version: str, changelog: str | None = None) -> dict:
        db = await get_db()
        cap = await self.get_by_id(cap_id)
        if not cap:
            raise ValueError(f"Capability {cap_id} not found")
        now = utcnow()
        record = {
            "id": new_id(),
            "capability_id": cap_id,
            "version": version,
            "snapshot": json.dumps(cap),
            "changelog": changelog,
            "created_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO capability_versions ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        record["snapshot"] = cap
        return record
