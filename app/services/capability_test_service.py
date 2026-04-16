from __future__ import annotations

import time
from typing import Any

from app.repositories.audit_repo import AuditRepo
from app.repositories.capability_repo import CapabilityRepo
from app.repositories.capability_test_repo import CapabilityTestRepo
from app.runtime.adapters.local_tools import get_capability_tools
from app.services.registry_service import RegistryService
from app.schemas.common import utcnow


class CapabilityTestService:
    def __init__(self):
        self.registry = RegistryService()
        self.repo = CapabilityRepo()
        self.test_repo = CapabilityTestRepo()
        self.audit = AuditRepo()

    async def run_test(self, capability_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:
        capability = await self.registry.get_capability(capability_id)
        if capability is None:
            raise ValueError(f"Capability {capability_id} not found")

        started = time.monotonic()
        status = "failed"
        response_payload: dict[str, Any] = {}
        error_message: str | None = None

        try:
            tool = self._resolve_single_tool(capability)
            raw_result = await self._invoke_tool(tool, request_payload)
            response_payload = {"result": str(raw_result)}
            status = "passed"
        except Exception as exc:
            error_message = str(exc)
            response_payload = {}

        latency_ms = int((time.monotonic() - started) * 1000)
        tested_at = utcnow()
        result = {
            "capability_id": capability_id,
            "status": status,
            "latency_ms": latency_ms,
            "request_payload": request_payload,
            "response_payload": response_payload,
            "error_message": error_message,
            "tested_at": tested_at,
        }

        if capability.get("is_builtin"):
            return result

        persisted = await self.test_repo.create(result)
        await self.repo.update(
            capability_id,
            {
                "last_test_status": status,
                "last_tested_at": tested_at,
                "last_latency_ms": latency_ms,
            },
        )
        await self.audit.log("test", "capability", capability_id, payload={"status": status})
        return persisted

    async def list_tests(self, capability_id: str, limit: int = 10) -> list[dict[str, Any]]:
        capability = await self.registry.get_capability(capability_id)
        if capability is None:
            raise ValueError(f"Capability {capability_id} not found")
        if capability.get("is_builtin"):
            return []
        return await self.test_repo.list_for_capability(capability_id, limit)

    @staticmethod
    def _resolve_single_tool(capability: dict[str, Any]):
        tools = get_capability_tools(capability, capability.get("connection_config") or {})
        if not tools:
            raise ValueError(f"Capability {capability.get('id') or capability.get('slug')} has no executable tool")
        return tools[0]

    @staticmethod
    async def _invoke_tool(tool: Any, request_payload: dict[str, Any]) -> Any:
        if hasattr(tool, "coroutine") and tool.coroutine:
            return await tool.coroutine(**request_payload)
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(request_payload)
        if hasattr(tool, "func"):
            return tool.func(**request_payload)
        if hasattr(tool, "invoke"):
            return tool.invoke(request_payload)
        raise ValueError(f"Tool {getattr(tool, 'name', '<unknown>')} is not executable")
