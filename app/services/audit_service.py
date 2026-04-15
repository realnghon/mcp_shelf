from app.repositories.audit_repo import AuditRepo


class AuditService:
    def __init__(self):
        self.repo = AuditRepo()

    async def list_logs(self, **kwargs) -> tuple[list[dict], int]:
        return await self.repo.list_all(**kwargs)

    async def get_target_logs(self, target_type: str, target_id: str) -> tuple[list[dict], int]:
        return await self.repo.list_all(target_type=target_type, target_id=target_id)
