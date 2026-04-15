import json
from typing import Any

import aiosqlite

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("runtime_overrides",):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    return d


class BindingRepo:
    async def list_all(
        self,
        visibility: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        db = await get_db()
        conditions = []
        params: list[Any] = []

        if visibility:
            conditions.append("visibility = ?")
            params.append(visibility)
        if search:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend(["%" + search + "%", "%" + search + "%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_sql = f"SELECT COUNT(*) FROM bindings {where}"
        data_sql = f"SELECT * FROM bindings {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"

        cursor = await db.execute(count_sql, params)
        total = (await cursor.fetchone())[0]
        cursor = await db.execute(data_sql, params + [page_size, (page - 1) * page_size])
        rows = await cursor.fetchall()
        return [dict(r) for r in rows], total

    async def get_by_id(self, binding_id: str) -> dict | None:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM bindings WHERE id = ?", [binding_id])
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create(self, data: dict[str, Any]) -> dict:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "name": data["name"],
            "description": data.get("description"),
            "model_key": data["model_key"],
            "system_prompt": data.get("system_prompt"),
            "max_steps": data.get("max_steps", 8),
            "temperature": data.get("temperature"),
            "allow_shell": int(data.get("allow_shell", False)),
            "owner_id": data.get("owner_id"),
            "visibility": data.get("visibility", "private"),
            "created_at": now,
            "updated_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO bindings ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        record["allow_shell"] = bool(record["allow_shell"])
        return record

    async def update(self, binding_id: str, data: dict[str, Any]) -> dict | None:
        db = await get_db()
        existing = await self.get_by_id(binding_id)
        if not existing:
            return None

        sets = []
        params: list[Any] = []
        for key, val in data.items():
            if val is None and key not in ("description", "system_prompt", "owner_id", "temperature"):
                continue
            if key == "allow_shell" and isinstance(val, bool):
                val = int(val)
            sets.append(f"{key} = ?")
            params.append(val)

        if not sets:
            return existing

        sets.append("updated_at = ?")
        params.append(utcnow())
        params.append(binding_id)
        await db.execute(f"UPDATE bindings SET {', '.join(sets)} WHERE id = ?", params)
        await db.commit()
        return await self.get_by_id(binding_id)

    async def delete(self, binding_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute("DELETE FROM bindings WHERE id = ?", [binding_id])
        await db.commit()
        return cursor.rowcount > 0

    # --- Binding Capabilities ---

    async def list_capabilities(self, binding_id: str) -> list[dict]:
        db = await get_db()
        cursor = await db.execute(
            """SELECT bc.*, c.name as capability_name, c.kind as capability_kind, c.slug as capability_slug
               FROM binding_capabilities bc
               JOIN capabilities c ON bc.capability_id = c.id
               WHERE bc.binding_id = ?
               ORDER BY bc.mount_order""",
            [binding_id],
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def add_capability(self, binding_id: str, data: dict[str, Any]) -> dict:
        db = await get_db()
        record = {
            "id": new_id(),
            "binding_id": binding_id,
            "capability_id": data["capability_id"],
            "is_enabled": int(data.get("is_enabled", True)),
            "mount_order": data.get("mount_order", 0),
            "runtime_overrides": json.dumps(data.get("runtime_overrides", {})),
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO binding_capabilities ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        record["is_enabled"] = bool(record["is_enabled"])
        record["runtime_overrides"] = data.get("runtime_overrides", {})
        return record

    async def remove_capability(self, binding_id: str, capability_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute(
            "DELETE FROM binding_capabilities WHERE binding_id = ? AND capability_id = ?",
            [binding_id, capability_id],
        )
        await db.commit()
        return cursor.rowcount > 0

    async def clone(self, binding_id: str) -> dict | None:
        existing = await self.get_by_id(binding_id)
        if not existing:
            return None
        caps = await self.list_capabilities(binding_id)

        new_binding = await self.create({
            "name": f"{existing['name']} (Copy)",
            "description": existing["description"],
            "model_key": existing["model_key"],
            "system_prompt": existing["system_prompt"],
            "max_steps": existing["max_steps"],
            "temperature": existing["temperature"],
            "allow_shell": bool(existing["allow_shell"]),
            "owner_id": existing["owner_id"],
            "visibility": existing["visibility"],
        })

        for cap in caps:
            await self.add_capability(new_binding["id"], {
                "capability_id": cap["capability_id"],
                "is_enabled": cap["is_enabled"],
                "mount_order": cap["mount_order"],
                "runtime_overrides": cap["runtime_overrides"],
            })

        return new_binding
