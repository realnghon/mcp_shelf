import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.main import app
from app.repositories.capability_repo import CapabilityRepo
import app.services.capability_test_service as capability_test_module
from app.services.capability_test_service import CapabilityTestService


@pytest.mark.asyncio
async def test_capability_test_service_executes_builtin_calculator():
    service = CapabilityTestService()

    result = await service.run_test(
        capability_id="builtin:calculator",
        request_payload={"expression": "2 + 3 * 4"},
    )

    assert result["status"] == "passed"
    assert result["response_payload"] == {"result": "14"}
    assert result["latency_ms"] is not None
    assert result["capability_id"] == "builtin:calculator"


@pytest.mark.asyncio
async def test_capability_test_service_persists_record_and_updates_capability(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        repo = CapabilityRepo()
        created = await repo.create(
            {
                "kind": "tool",
                "name": "Calculator",
                "slug": "calculator-copy",
                "type": "tool",
                "source_type": "custom",
                "source_id": "calculator-copy",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "string"},
                "connection_config": {},
            }
        )

        service = CapabilityTestService()
        result = await service.run_test(
            capability_id=created["id"],
            request_payload={"expression": "1 + 2"},
        )

        assert result["status"] == "failed"
        assert result["capability_id"] == created["id"]

        stored = await repo.get_by_id(created["id"])
        assert stored is not None
        assert stored["last_test_status"] == "failed"
        assert stored["last_tested_at"] is not None
        assert stored["last_latency_ms"] is not None

        history = await service.list_tests(created["id"])
        assert len(history) == 1
        assert history[0]["status"] == "failed"
        assert history[0]["request_payload"] == {"expression": "1 + 2"}
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


@pytest.mark.asyncio
async def test_capability_test_service_executes_mcp_tool_when_capability_is_mcp(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    class _DummyMcpTool:
        name = "dummy_mcp_echo"

        @staticmethod
        async def ainvoke(payload):
            return f"mcp-ok:{payload.get('message', '')}"

    async def _mock_get_mcp_tools(_config):
        return [_DummyMcpTool()]

    monkeypatch.setattr(capability_test_module, "get_mcp_tools", _mock_get_mcp_tools)

    try:
        await run_migrations()
        repo = CapabilityRepo()
        created = await repo.create(
            {
                "kind": "mcp",
                "name": "Mock MCP Capability",
                "slug": "mock-mcp-capability",
                "type": "tool",
                "source_type": "mcp_server",
                "source_id": "mcp.mock-mcp-capability",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "connection_config": {
                    "transport": "streamable_http",
                    "endpoint_url": "http://localhost:3000/mcp",
                },
            }
        )

        service = CapabilityTestService()
        result = await service.run_test(
            capability_id=created["id"],
            request_payload={"message": "ping"},
        )

        assert result["status"] == "passed"
        assert result["capability_id"] == created["id"]
        assert result["response_payload"] == {"result": "mcp-ok:ping"}
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_capability_test_api_runs_builtin_calculator():
    with TestClient(app) as client:
        response = client.post(
            "/api/capabilities/builtin:calculator/test",
            json={"request_payload": {"expression": "5 * 5"}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "passed"
    assert payload["response_payload"] == {"result": "25"}
