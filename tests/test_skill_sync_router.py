import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.routers.skills as skills_router_module


def test_sync_superpowers_router_success(monkeypatch):
    async def fake_sync(pack: str):
        assert pack == "superpowers"
        return {"ok": True, "pack": "superpowers", "skill_count": 14}

    monkeypatch.setattr(skills_router_module.svc, "sync_pack", fake_sync)
    with TestClient(app) as client:
        response = client.post("/api/skills/sync/superpowers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["pack"] == "superpowers"
    assert payload["skill_count"] == 14


def test_sync_superpowers_router_error(monkeypatch):
    async def fake_sync(pack: str):
        assert pack == "superpowers"
        raise RuntimeError("network timeout")

    monkeypatch.setattr(skills_router_module.svc, "sync_pack", fake_sync)
    with TestClient(app) as client:
        response = client.post("/api/skills/sync/superpowers")

    assert response.status_code == 500
    assert "Sync skill pack failed" in response.json()["detail"]
