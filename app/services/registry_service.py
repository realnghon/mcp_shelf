from typing import Any

from app.repositories.audit_repo import AuditRepo
from app.repositories.capability_repo import CapabilityRepo
from app.runtime.adapters.builtin_catalog import load_builtin_capabilities
from app.schemas.capability import CapabilityCreate, CapabilityUpdate


class RegistryService:
    def __init__(self):
        self.repo = CapabilityRepo()
        self.audit = AuditRepo()

    async def list_capabilities(
        self,
        include_builtin: bool = True,
        **kwargs,
    ) -> tuple[list[dict], int]:
        records, total = await self.repo.list_all(**kwargs)
        if not include_builtin:
            return records, total

        builtin_items = self._filter_builtin_capabilities(load_builtin_capabilities(), **kwargs)
        return builtin_items + records, total + len(builtin_items)

    async def get_capability(self, cap_id: str) -> dict | None:
        if cap_id.startswith("builtin:"):
            return self._get_builtin_capability(cap_id)
        return await self.repo.get_by_id(cap_id)

    async def get_by_slug(self, slug: str) -> dict | None:
        return await self.repo.get_by_slug(slug)

    async def create_capability(self, data: CapabilityCreate, actor_id: str | None = None) -> dict:
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise ValueError(f"Slug '{data.slug}' already exists")
        record = await self.repo.create(data.model_dump())
        await self.audit.log("create", "capability", record["id"], actor_id)
        return record

    async def update_capability(
        self,
        cap_id: str,
        data: CapabilityUpdate,
        actor_id: str | None = None,
    ) -> dict | None:
        update_data = data.model_dump(exclude_none=True)
        record = await self.repo.update(cap_id, update_data)
        if record:
            await self.audit.log("update", "capability", cap_id, actor_id)
        return record

    async def delete_capability(self, cap_id: str, actor_id: str | None = None) -> bool:
        ok = await self.repo.delete(cap_id)
        if ok:
            await self.audit.log("delete", "capability", cap_id, actor_id)
        return ok

    async def activate(self, cap_id: str, actor_id: str | None = None) -> dict | None:
        record = await self.repo.set_status(cap_id, "active")
        if record:
            await self.audit.log("activate", "capability", cap_id, actor_id)
        return record

    async def deactivate(self, cap_id: str, actor_id: str | None = None) -> dict | None:
        record = await self.repo.set_status(cap_id, "inactive")
        if record:
            await self.audit.log("deactivate", "capability", cap_id, actor_id)
        return record

    async def list_versions(self, cap_id: str) -> list[dict]:
        return await self.repo.list_versions(cap_id)

    async def create_version(self, cap_id: str, changelog: str | None = None) -> dict:
        cap = await self.repo.get_by_id(cap_id)
        if not cap:
            raise ValueError(f"Capability {cap_id} not found")
        return await self.repo.create_version(cap_id, cap["version"], changelog)

    @staticmethod
    def _filter_builtin_capabilities(
        capabilities: list[dict[str, Any]],
        **kwargs,
    ) -> list[dict[str, Any]]:
        kind = kwargs.get("kind")
        status = kwargs.get("status")
        category = kwargs.get("category")
        search = kwargs.get("search")
        page = kwargs.get("page", 1)
        page_size = kwargs.get("page_size", 20)
        sort_by = kwargs.get("sort_by", "updated_at")
        sort_order = kwargs.get("sort_order", "desc")

        filtered = capabilities
        if kind:
            filtered = [cap for cap in filtered if cap.get("kind") == kind]
        if status:
            filtered = [cap for cap in filtered if cap.get("status") == status]
        if category:
            filtered = [cap for cap in filtered if cap.get("category") == category]
        if search:
            needle = search.lower()
            filtered = [
                cap for cap in filtered
                if needle in (cap.get("name") or "").lower()
                or needle in (cap.get("description") or "").lower()
            ]

        reverse = str(sort_order).lower() != "asc"
        if sort_by == "name":
            filtered = sorted(filtered, key=lambda item: str(item.get("name", "")).lower(), reverse=reverse)
        elif sort_by == "version":
            filtered = sorted(filtered, key=lambda item: str(item.get("version", "")).lower(), reverse=reverse)
        elif sort_by == "schema_status":
            filtered = sorted(filtered, key=lambda item: str(item.get("schema_status", "")), reverse=reverse)
        elif sort_by == "last_test_status":
            filtered = sorted(filtered, key=lambda item: str(item.get("last_test_status", "")), reverse=reverse)

        start = max(page - 1, 0) * page_size
        end = start + page_size
        return filtered[start:end]

    @staticmethod
    def _get_builtin_capability(cap_id: str) -> dict[str, Any] | None:
        for capability in load_builtin_capabilities():
            if capability.get("id") == cap_id:
                return capability
        return None
