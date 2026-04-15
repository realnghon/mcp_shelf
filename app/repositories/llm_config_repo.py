import json
from typing import Any, Optional

from app.core.db import get_db
from app.schemas.common import new_id, utcnow


class LLMConfigRepo:
    async def list_all(self) -> list[dict]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM llm_configs ORDER BY is_default DESC, name"
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["extra_config"] = json.loads(d["extra_config"]) if isinstance(d["extra_config"], str) else d["extra_config"]
            d["is_default"] = bool(d.get("is_default", 0))
            results.append(d)
        return results

    async def get_by_id(self, config_id: str) -> Optional[dict]:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM llm_configs WHERE id = ?", [config_id])
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["extra_config"] = json.loads(d["extra_config"]) if isinstance(d["extra_config"], str) else d["extra_config"]
        d["is_default"] = bool(d.get("is_default", 0))
        return d

    async def get_default(self) -> Optional[dict]:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM llm_configs WHERE is_default = 1 LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["extra_config"] = json.loads(d["extra_config"]) if isinstance(d["extra_config"], str) else d["extra_config"]
        d["is_default"] = True
        return d

    async def get_by_provider(self, provider: str) -> Optional[dict]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM llm_configs WHERE provider = ? LIMIT 1", [provider]
        )
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["extra_config"] = json.loads(d["extra_config"]) if isinstance(d["extra_config"], str) else d["extra_config"]
        d["is_default"] = bool(d.get("is_default", 0))
        return d

    async def create(self, data: dict[str, Any]) -> dict:
        db = await get_db()
        now = utcnow()
        record = {
            "id": new_id(),
            "provider": data["provider"],
            "name": data["name"],
            "api_key": data.get("api_key"),
            "base_url": data.get("base_url"),
            "default_model": data.get("default_model"),
            "is_default": int(data.get("is_default", False)),
            "extra_config": json.dumps(data.get("extra_config", {})),
            "created_at": now,
            "updated_at": now,
        }
        cols = ", ".join(record.keys())
        placeholders = ", ".join(["?"] * len(record))
        await db.execute(f"INSERT INTO llm_configs ({cols}) VALUES ({placeholders})", list(record.values()))
        await db.commit()
        record["is_default"] = bool(record["is_default"])
        record["extra_config"] = data.get("extra_config", {})
        return record

    async def update(self, config_id: str, data: dict[str, Any]) -> Optional[dict]:
        db = await get_db()
        existing = await self.get_by_id(config_id)
        if not existing:
            return None

        sets = []
        params: list[Any] = []
        for key, val in data.items():
            if val is None and key not in ("api_key", "base_url", "default_model"):
                continue
            if key == "is_default" and isinstance(val, bool):
                val = int(val)
            if key == "extra_config":
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)

        if not sets:
            return existing

        sets.append("updated_at = ?")
        params.append(utcnow())
        params.append(config_id)
        await db.execute(f"UPDATE llm_configs SET {', '.join(sets)} WHERE id = ?", params)
        await db.commit()
        return await self.get_by_id(config_id)

    async def delete(self, config_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute("DELETE FROM llm_configs WHERE id = ?", [config_id])
        await db.commit()
        return cursor.rowcount > 0
