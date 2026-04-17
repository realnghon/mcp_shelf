import asyncio

from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.main import app
from app.repositories.binding_repo import BindingRepo
from app.repositories.capability_repo import CapabilityRepo
from app.runtime.nodes.build_tools import build_tools_node
from app.runtime.state import AgentState


def test_bindings_new_page_exists():
    with TestClient(app) as client:
        response = client.get("/bindings/new")
    assert response.status_code == 200
    assert "New Binding" in response.text


def test_ops_page_exists():
    with TestClient(app) as client:
        response = client.get("/ops")
    assert response.status_code == 200
    assert "Operations" in response.text


def test_capabilities_category_buttons_render_clickable_onclick():
    with TestClient(app) as client:
        response = client.get("/capabilities")

    assert response.status_code == 200
    html = response.text
    assert 'onclick=\'selectCategory("memory")\'' in html
    assert 'onclick="selectCategory("memory")"' not in html


def test_capabilities_api_supports_sorting(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        async def seed():
            await run_migrations()
            repo = CapabilityRepo()
            await repo.create(
                {
                    "kind": "tool",
                    "name": "Zeta",
                    "slug": "zeta",
                    "type": "tool",
                    "source_type": "custom",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            )
            await repo.create(
                {
                    "kind": "tool",
                    "name": "Alpha",
                    "slug": "alpha",
                    "type": "tool",
                    "source_type": "custom",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            )
        asyncio.run(seed())

        with TestClient(app) as client:
            response = client.get("/api/capabilities?sort_by=name&sort_order=asc&page_size=10")
        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"] if not str(item["id"]).startswith("builtin:")]
        assert names[:2] == ["Alpha", "Zeta"]
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_build_tools_node_treats_skill_capability_as_prompt_fragment(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        async def seed_and_build():
            await run_migrations()
            cap_repo = CapabilityRepo()
            bind_repo = BindingRepo()

            skill_cap = await cap_repo.create(
                {
                    "kind": "skill",
                    "name": "Safety Policy",
                    "slug": "safety-policy",
                    "type": "prompt",
                    "source_type": "custom",
                    "connection_config": {"prompt": "Always answer with explicit safety checks."},
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            )
            binding = await bind_repo.create(
                {
                    "name": "Test Binding",
                    "model_key": "openai:gpt-4.1",
                }
            )
            await bind_repo.add_capability(
                binding["id"],
                {
                    "capability_id": skill_cap["id"],
                    "is_enabled": True,
                    "mount_order": 0,
                    "runtime_overrides": {},
                },
            )
            state: AgentState = {
                "thread_id": "th_1",
                "session_id": "sess_1",
                "binding_id": binding["id"],
                "model_key": "openai:gpt-4.1",
                "messages": [{"role": "user", "content": "hello"}],
                "selected_capabilities": [
                    {
                        "capability_id": skill_cap["id"],
                        "kind": "skill",
                        "slug": "safety-policy",
                        "is_enabled": True,
                        "runtime_overrides": {},
                        "connection_config": {},
                    }
                ],
                "available_tools": [],
                "max_steps": 8,
                "current_step": 0,
                "final_output": None,
                "error": None,
            }
            return await build_tools_node(state)

        result = asyncio.run(seed_and_build())
        tool_names = [getattr(tool, "name", "") for tool in result["available_tools"]]
        assert "skill_safety-policy" not in tool_names
        system_msgs = [
            msg for msg in result.get("messages", []) if isinstance(msg, dict) and msg.get("role") == "system"
        ]
        assert any("Always answer with explicit safety checks." in (msg.get("content") or "") for msg in system_msgs)
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None
