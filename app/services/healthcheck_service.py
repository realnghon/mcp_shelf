import time

import httpx

from app.repositories.capability_repo import CapabilityRepo
from app.repositories.health_repo import HealthRepo
from app.repositories.audit_repo import AuditRepo


class HealthcheckService:
    def __init__(self):
        self.cap_repo = CapabilityRepo()
        self.health_repo = HealthRepo()
        self.audit = AuditRepo()

    async def check_capability(self, capability_id: str) -> dict:
        cap = await self.cap_repo.get_by_id(capability_id)
        if not cap:
            raise ValueError(f"Capability {capability_id} not found")

        await self.health_repo.ensure_discovery_status_column()

        if cap["kind"] != "mcp":
            record = await self.health_repo.create(
                capability_id,
                "ok",
                detail="Non-MCP capability",
                discovery_status="not_applicable",
            )
            return record

        config = cap["connection_config"]
        endpoint = config.get("endpoint_url", "")

        if not endpoint:
            record = await self.health_repo.create(
                capability_id,
                "failed",
                detail="No endpoint configured",
                discovery_status="unavailable",
            )
            return record

        try:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(endpoint)
            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code < 500:
                status = "ok"
                detail = f"HTTP {resp.status_code}"
                discovery_status = "available"
            else:
                status = "degraded"
                detail = f"HTTP {resp.status_code}"
                discovery_status = "degraded"

            record = await self.health_repo.create(
                capability_id,
                status,
                latency_ms,
                detail,
                discovery_status=discovery_status,
            )
        except Exception as e:
            record = await self.health_repo.create(
                capability_id,
                "failed",
                detail=str(e),
                discovery_status="unavailable",
            )

        await self.audit.log("healthcheck", "capability", capability_id)
        return record

    async def get_summary(self) -> list[dict]:
        return await self.health_repo.get_summary()

    async def get_capability_history(self, capability_id: str, limit: int = 10) -> list[dict]:
        return await self.health_repo.list_for_capability(capability_id, limit)
