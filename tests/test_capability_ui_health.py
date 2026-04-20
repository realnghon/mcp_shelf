import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.main import app
from app.repositories.capability_repo import CapabilityRepo
from app.services.healthcheck_service import HealthcheckService


@pytest.mark.asyncio
async def test_healthcheck_service_reports_mcp_discovery_details(tmp_path):
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
                "name": "Weather MCP",
                "slug": "weather-mcp",
                "type": "tool",
                "source_type": "mcp_server",
                "source_id": "mcp.weather",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "connection_config": {},
            }
        )

        service = HealthcheckService()
        result = await service.check_capability(created["id"])

        assert result["status"] == "failed"
        assert result["detail"] == "No endpoint configured"
        assert result["discovery_status"] == "unavailable"
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


@pytest.mark.asyncio
async def test_health_summary_includes_discovery_status(tmp_path):
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
                "name": "Weather MCP",
                "slug": "weather-mcp",
                "type": "tool",
                "source_type": "mcp_server",
                "source_id": "mcp.weather",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "connection_config": {},
            }
        )

        service = HealthcheckService()
        await service.check_capability(created["id"])
        summary = await service.get_summary()

        weather = next(item for item in summary if item["id"] == created["id"])
        assert weather["health_status"] == "failed"
        assert weather["discovery_status"] == "unavailable"
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_capability_detail_page_shows_test_and_health_sections(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:

        async def seed():
            await run_migrations()
            repo = CapabilityRepo()
            return await repo.create(
                {
                    "kind": "mcp",
                    "name": "Weather MCP",
                    "slug": "weather-mcp",
                    "type": "tool",
                    "source_type": "mcp_server",
                    "source_id": "mcp.weather",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "connection_config": {},
                }
            )

        created = asyncio.run(seed())

        with TestClient(app) as client:
            response = client.get(f"/capabilities/{created['id']}")

        assert response.status_code == 200
        html = response.text
        assert "Schema Status" in html
        assert "Latest Test" in html
        assert "Health Check" in html
        assert "Health History" not in html
        assert "setTimeout(() => location.reload()" not in html
        assert "id=\"health-check-btn\"" in html
        assert "id=\"run-test-btn\"" in html
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None
