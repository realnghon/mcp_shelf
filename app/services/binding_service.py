from app.repositories.binding_repo import BindingRepo
from app.repositories.audit_repo import AuditRepo
from app.schemas.binding import BindingCreate, BindingUpdate, BindingCapabilityAdd


class BindingService:
    def __init__(self):
        self.repo = BindingRepo()
        self.audit = AuditRepo()

    async def list_bindings(self, **kwargs) -> tuple[list[dict], int]:
        items, total = await self.repo.list_all(**kwargs)
        # Attach capabilities for each binding
        for item in items:
            item["capabilities"] = await self.repo.list_capabilities(item["id"])
            item["allow_shell"] = bool(item.get("allow_shell", 0))
        return items, total

    async def get_binding(self, binding_id: str) -> dict | None:
        record = await self.repo.get_by_id(binding_id)
        if record:
            record["capabilities"] = await self.repo.list_capabilities(binding_id)
            record["allow_shell"] = bool(record.get("allow_shell", 0))
        return record

    async def create_binding(self, data: BindingCreate, actor_id: str | None = None) -> dict:
        record = await self.repo.create(data.model_dump())
        await self.audit.log("create", "binding", record["id"], actor_id)
        return record

    async def update_binding(self, binding_id: str, data: BindingUpdate, actor_id: str | None = None) -> dict | None:
        update_data = data.model_dump(exclude_none=True)
        record = await self.repo.update(binding_id, update_data)
        if record:
            await self.audit.log("update", "binding", binding_id, actor_id)
        return record

    async def delete_binding(self, binding_id: str, actor_id: str | None = None) -> bool:
        ok = await self.repo.delete(binding_id)
        if ok:
            await self.audit.log("delete", "binding", binding_id, actor_id)
        return ok

    async def add_capability(self, binding_id: str, data: BindingCapabilityAdd, actor_id: str | None = None) -> dict:
        record = await self.repo.add_capability(binding_id, data.model_dump())
        await self.audit.log("add_capability", "binding", binding_id, actor_id,
                             {"capability_id": data.capability_id})
        return record

    async def remove_capability(self, binding_id: str, capability_id: str, actor_id: str | None = None) -> bool:
        ok = await self.repo.remove_capability(binding_id, capability_id)
        if ok:
            await self.audit.log("remove_capability", "binding", binding_id, actor_id,
                                 {"capability_id": capability_id})
        return ok

    async def clone_binding(self, binding_id: str, actor_id: str | None = None) -> dict | None:
        record = await self.repo.clone(binding_id)
        if record:
            await self.audit.log("clone", "binding", record["id"], actor_id,
                                 {"source_binding_id": binding_id})
        return record
