import pytest

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.runtime.adapters.builtin_catalog import load_builtin_capabilities
from app.services.registry_service import RegistryService


def test_load_builtin_capabilities_exposes_calculator_manifest():
    capabilities = load_builtin_capabilities()

    calculator = next(cap for cap in capabilities if cap["id"] == "builtin:calculator")
    assert calculator["source_type"] == "builtin"
    assert calculator["type"] == "tool"
    assert calculator["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_registry_service_get_capability_returns_builtin_calculator(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        service = RegistryService()

        calculator = await service.get_capability("builtin:calculator")

        assert calculator is not None
        assert calculator["id"] == "builtin:calculator"
        assert calculator["source_type"] == "builtin"
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None
