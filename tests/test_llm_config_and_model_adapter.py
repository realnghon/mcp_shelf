import asyncio

from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.main import app
from app.runtime.adapters.models import _normalize_base_url


def test_normalize_base_url_adds_v1_for_custom_openai_compatible_provider():
    assert _normalize_base_url("custom", "https://api.example.com") == "https://api.example.com/v1"
    assert _normalize_base_url("custom", "https://api.example.com/v1") == "https://api.example.com/v1"


def test_llm_config_update_can_change_provider(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        asyncio.run(run_migrations())
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/llm-configs",
                json={
                    "provider": "custom",
                    "name": "test-provider",
                    "base_url": "https://api.example.com",
                    "default_model": "z-ai/glm-5.1",
                    "is_default": True,
                },
            )
            assert create_resp.status_code == 201
            cfg_id = create_resp.json()["id"]

            update_resp = client.put(
                f"/api/llm-configs/{cfg_id}",
                json={
                    "provider": "openai",
                    "name": "test-provider-updated",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-4.1",
                },
            )
            assert update_resp.status_code == 200
            payload = update_resp.json()
            assert payload["provider"] == "openai"
            assert payload["name"] == "test-provider-updated"
            assert payload["default_model"] == "gpt-4.1"
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None
