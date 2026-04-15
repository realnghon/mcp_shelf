from typing import Any

from app.repositories.capability_repo import CapabilityRepo
from app.repositories.audit_repo import AuditRepo
from app.schemas.capability import CapabilityCreate, CapabilityUpdate


class RegistryService:
    def __init__(self):
        self.repo = CapabilityRepo()
        self.audit = AuditRepo()

    async def list_capabilities(self, **kwargs) -> tuple[list[dict], int]:
        return await self.repo.list_all(**kwargs)

    async def get_capability(self, cap_id: str) -> dict | None:
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

    async def update_capability(self, cap_id: str, data: CapabilityUpdate, actor_id: str | None = None) -> dict | None:
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
