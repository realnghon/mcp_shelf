import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.main import app
from app.repositories.capability_repo import CapabilityRepo
from app.runtime.adapters.builtin_catalog import load_builtin_capabilities
from app.services.capability_validation_service import CapabilityValidationService


@pytest.mark.asyncio
async def test_capability_validation_service_accepts_builtin_calculator_definition():
    service = CapabilityValidationService()

    calculator = next(cap for cap in load_builtin_capabilities() if cap["id"] == "builtin:calculator")
    result = await service.validate_definition(calculator)

    assert result["valid"] is True
    assert result["schema_status"] == "valid"
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_capability_validation_service_rejects_mcp_server_without_endpoint():
    service = CapabilityValidationService()

    result = await service.validate_definition(
        {
            "kind": "mcp",
            "name": "Broken MCP",
            "slug": "broken-mcp",
            "type": "tool",
            "source_type": "mcp_server",
            "connection_config": {},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }
    )

    assert result["valid"] is False
    assert result["schema_status"] == "invalid"
    assert any("endpoint_url" in error for error in result["errors"])


@pytest.mark.asyncio
async def test_validate_capability_api_updates_schema_status_for_stored_capability(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        repo = CapabilityRepo()
        created = await repo.create(
            {
                "kind": "mcp",
                "name": "Weather SSE",
                "slug": "weather-sse",
                "type": "tool",
                "source_type": "mcp_server",
                "source_id": "mcp.weather",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "connection_config": {"endpoint_url": "https://example.com/sse"},
            }
        )

        with TestClient(app) as client:
            response = client.post("/api/capabilities/validate", json={"capability_id": created["id"]})

        assert response.status_code == 200
        payload = response.json()
        assert payload["valid"] is True
        assert payload["schema_status"] == "valid"
        assert payload["capability_id"] == created["id"]

        stored = await repo.get_by_id(created["id"])
        assert stored is not None
        assert stored["schema_status"] == "valid"
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None
