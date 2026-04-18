import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.repositories.health_repo import HealthRepo
from app.repositories.audit_repo import AuditRepo
from app.runtime.adapters.local_tools import get_capability_tools
from app.schemas.common import utcnow
from app.services.registry_service import RegistryService


class HealthcheckService:
    def __init__(self):
        self.registry = RegistryService()
        self.health_repo = HealthRepo()
        self.audit = AuditRepo()

    async def check_capability(self, capability_id: str) -> dict:
        cap = await self.registry.get_capability(capability_id)
        if not cap:
            raise ValueError(f"Capability {capability_id} not found")

        await self.health_repo.ensure_discovery_status_column()

        if cap["kind"] == "mcp":
            record = await self._check_mcp(cap)
        elif cap["kind"] == "tool":
            record = await self._check_tool(cap)
        else:
            record = await self._record_health(
                cap=cap,
                status="ok",
                detail="Non-MCP capability",
                discovery_status="not_applicable",
            )

        await self.audit.log("healthcheck", "capability", capability_id)
        return record

    async def _check_tool(self, cap: dict[str, Any]) -> dict:
        started = time.monotonic()
        try:
            tools = get_capability_tools(cap, cap.get("connection_config") or {})
            if not tools:
                return await self._record_health(
                    cap=cap,
                    status="failed",
                    detail="No executable tool resolved from capability config",
                    discovery_status="unavailable",
                )

            tool = tools[0]
            request_payload = self._sample_payload_for(cap)
            raw_result = await self._invoke_tool(tool, request_payload)
            status, detail = self._evaluate_tool_result(raw_result)
            latency_ms = int((time.monotonic() - started) * 1000)
            return await self._record_health(
                cap=cap,
                status=status,
                latency_ms=latency_ms,
                detail=detail,
                discovery_status="available" if status == "ok" else "degraded",
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return await self._record_health(
                cap=cap,
                status="failed",
                latency_ms=latency_ms,
                detail=str(exc),
                discovery_status="unavailable",
            )

    async def _check_mcp(self, cap: dict[str, Any]) -> dict:
        config = cap.get("connection_config") or {}
        endpoint = config.get("endpoint_url", "")

        if not endpoint:
            return await self._record_health(
                cap=cap,
                status="failed",
                detail="No endpoint configured",
                discovery_status="unavailable",
            )

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

            return await self._record_health(
                cap=cap,
                status=status,
                latency_ms=latency_ms,
                detail=detail,
                discovery_status=discovery_status,
            )
        except Exception as exc:
            return await self._record_health(
                cap=cap,
                status="failed",
                detail=str(exc),
                discovery_status="unavailable",
            )

    async def _record_health(
        self,
        cap: dict[str, Any],
        status: str,
        latency_ms: int | None = None,
        detail: str | None = None,
        discovery_status: str | None = None,
    ) -> dict[str, Any]:
        if cap.get("is_builtin"):
            return {
                "id": f"builtin-health:{cap['id']}:{int(time.time())}",
                "capability_id": cap["id"],
                "status": status,
                "latency_ms": latency_ms,
                "detail": detail,
                "discovery_status": discovery_status,
                "checked_at": utcnow(),
            }
        return await self.health_repo.create(
            capability_id=cap["id"],
            status=status,
            latency_ms=latency_ms,
            detail=detail,
            discovery_status=discovery_status,
        )

    async def _probe_mcp_discovery(self, endpoint: str) -> tuple[str, str]:
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
        except Exception as exc:
            return "unavailable", f"probe error: {exc}"

    async def get_summary(self) -> list[dict]:
        return await self.health_repo.get_summary()

    async def get_capability_history(self, capability_id: str, limit: int = 10) -> list[dict]:
        cap = await self.registry.get_capability(capability_id)
        if cap and cap.get("is_builtin"):
            return []
        return await self.health_repo.list_for_capability(capability_id, limit)

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

    @staticmethod
    def _evaluate_tool_result(raw_result: Any) -> tuple[str, str]:
        parsed: Any = raw_result
        if isinstance(raw_result, str):
            try:
                parsed = json.loads(raw_result)
            except Exception:
                parsed = raw_result

        if isinstance(parsed, dict):
            if parsed.get("ok") is False:
                return "failed", f"Tool returned ok=false: {json.dumps(parsed, ensure_ascii=False)[:400]}"
            if str(parsed.get("status", "")).lower() in {"error", "failed"}:
                return "failed", f"Tool returned error status: {json.dumps(parsed, ensure_ascii=False)[:400]}"

        if isinstance(raw_result, str) and raw_result.strip().lower().startswith("error:"):
            return "failed", raw_result[:400]

        return "ok", f"Tool executed successfully: {str(raw_result)[:220]}"

    @staticmethod
    def _sample_payload_for(capability: dict[str, Any]) -> dict[str, Any]:
        slug = str(capability.get("slug") or "")
        health_dir = settings.data_dir / "healthcheck"
        health_dir.mkdir(parents=True, exist_ok=True)

        if slug == "code-run":
            return {"script": "print('health-ok')", "type": "python", "timeout": 8}
        if slug == "calculator":
            return {"expression": "2 + 3 * 4"}
        if slug == "http-fetch":
            path = (health_dir / "http_fetch_smoke.txt").resolve()
            path.write_text("http-fetch-health-ok", encoding="utf-8")
            return {"url": path.as_uri(), "timeout_s": 5}
        if slug == "file-read":
            return {"path": str(Path("README.md").resolve()), "start": 1, "count": 20}
        if slug == "file-write":
            path = health_dir / "file_write_smoke.txt"
            return {"path": str(path), "content": "health-check", "mode": "overwrite"}
        if slug == "file-patch":
            path = health_dir / "file_patch_smoke.txt"
            path.write_text("hello world", encoding="utf-8")
            return {"path": str(path), "old_content": "hello", "new_content": "health"}
        if slug == "web-scan":
            return {"tabs_only": True}
        if slug == "web-execute-js":
            path = (health_dir / "web_execute_smoke.html").resolve()
            path.write_text("<html><body>web-execute-health-ok</body></html>", encoding="utf-8")
            return {"script": f"open {path.as_uri()}"}
        if slug == "ask-user":
            return {"question": "health-check", "candidates": ["ok"]}
        if slug == "update-working-checkpoint":
            return {"key_info": "health-check-memory", "related_sop": "health-sop"}
        if slug == "start-long-term-update":
            memory_dir = settings.data_dir / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            (memory_dir / "working_checkpoint.json").write_text(
                json.dumps(
                    {"key_info": "health-check-memory", "related_sop": "health-sop", "updated_at": utcnow()},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {}

        schema = capability.get("input_schema") or {}
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        payload: dict[str, Any] = {}
        for key, prop in properties.items():
            if key not in required:
                continue
            typ = str((prop or {}).get("type") or "")
            if typ == "string":
                payload[key] = "sample"
            elif typ in {"number", "integer"}:
                payload[key] = 0
            elif typ == "boolean":
                payload[key] = False
            elif typ == "array":
                payload[key] = []
            else:
                payload[key] = None
        return payload
