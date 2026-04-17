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
                discovery_status, discovery_detail = await self._probe_mcp_discovery(endpoint)
                detail = f"HTTP {resp.status_code}; discovery={discovery_detail}"
            else:
                status = "degraded"
                discovery_status = "degraded"
                detail = f"HTTP {resp.status_code}; discovery probe skipped"

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

    async def _probe_mcp_discovery(self, endpoint: str) -> tuple[str, str]:
        """Probe MCP discovery beyond plain connectivity.

        Returns:
        - discovery_status: available | degraded | unavailable
        - detail: concise probe result
        """
        candidates = [endpoint.rstrip("/"), endpoint.rstrip("/") + "/.well-known/mcp"]
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                for url in candidates:
                    resp = await client.get(url)
                    content_type = (resp.headers.get("content-type") or "").lower()
                    if resp.status_code >= 500:
                        continue
                    if "application/json" in content_type:
                        body = resp.json() if resp.text else {}
                        if isinstance(body, dict) and (
                            "capabilities" in body
                            or "tools" in body
                            or "servers" in body
                        ):
                            return "available", f"metadata discovered from {url}"
                        return "degraded", f"json response from {url} without capability metadata"
                    if "text/event-stream" in content_type:
                        return "available", f"SSE endpoint detected at {url}"
                    if resp.status_code < 400:
                        return "degraded", f"reachable {url} but no MCP metadata"
            return "unavailable", "no discovery endpoint responded with MCP metadata"
        except Exception as e:
            return "unavailable", f"probe error: {e}"

    async def get_summary(self) -> list[dict]:
        return await self.health_repo.get_summary()

    async def get_capability_history(self, capability_id: str, limit: int = 10) -> list[dict]:
        return await self.health_repo.list_for_capability(capability_id, limit)
