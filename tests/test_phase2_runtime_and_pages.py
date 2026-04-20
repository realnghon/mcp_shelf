import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.migrations import run_migrations
from app.main import app
from app.repositories.binding_repo import BindingRepo
from app.repositories.capability_repo import CapabilityRepo
from app.runtime.assembly.capability_resolver import resolve_selected_capabilities
from app.runtime.nodes.build_tools import build_tools_node
from app.runtime.state import AgentState


def test_bindings_new_page_exists():
    with TestClient(app) as client:
        response = client.get("/bindings/new")
    assert response.status_code == 200
    assert "New Binding" in response.text


def test_startup_seeds_superpowers_skill_capability(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        with TestClient(app) as client:
            response = client.get("/api/capabilities?kind=skill&search=superpowers")
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(item.get("slug") == "superpowers-using-superpowers" for item in items)
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_bindings_form_uses_settings_based_model_options_not_provider_model_dropdowns():
    with TestClient(app) as client:
        response = client.get("/bindings/new")

    assert response.status_code == 200
    html = response.text
    assert "/api/llm-configs" in html
    assert 'id="provider-select"' not in html
    assert 'id="model-select"' not in html


def test_binding_detail_page_uses_capability_checkboxes_instead_of_single_select(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        async def seed():
            await run_migrations()
            cap_repo = CapabilityRepo()
            bind_repo = BindingRepo()
            cap = await cap_repo.create(
                {
                    "kind": "tool",
                    "name": "Multi Add Test Capability",
                    "slug": "multi-add-test-capability",
                    "type": "tool",
                    "source_type": "custom",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            )
            binding = await bind_repo.create(
                {
                    "name": "Capability Multi Select Binding",
                    "model_key": "openai:gpt-4.1",
                }
            )
            return binding["id"], cap["id"]

        binding_id, capability_id = asyncio.run(seed())

        with TestClient(app) as client:
            response = client.get(f"/bindings/{binding_id}")

        assert response.status_code == 200
        html = response.text
        assert 'id="capability-select"' not in html
        assert f'data-capability-id="{capability_id}"' in html
        assert 'class="capability-add-checkbox"' in html
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_ops_page_is_not_exposed():
    with TestClient(app) as client:
        response = client.get("/ops")
    assert response.status_code == 404


def test_capabilities_new_page_shows_mcp_guided_form():
    with TestClient(app) as client:
        response = client.get("/capabilities/new")

    assert response.status_code == 200
    html = response.text
    assert "MCP Setup Guide" in html
    assert "Capability Kind" in html
    assert "Skill Setup Guide" in html
    assert "Use stdio example" in html
    assert "Use streamable HTTP example" in html
    assert "Advanced Settings" in html


@pytest.mark.asyncio
async def test_skill_capability_path_directory_mount_reads_skill_md(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        await run_migrations()
        repo = CapabilityRepo()
        skill_dir = tmp_path / "skills" / "email_helper"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("Use this skill to send email safely.", encoding="utf-8")
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(parents=True, exist_ok=True)
        (refs_dir / "tips.md").write_text("Always ask user confirmation before sending.", encoding="utf-8")

        capability = await repo.create(
            {
                "kind": "skill",
                "name": "Email Helper",
                "slug": "email-helper",
                "type": "prompt",
                "source_type": "custom",
                "connection_config": {"path": str(skill_dir), "include_files": ["references/tips.md"]},
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            }
        )

        resolved = await resolve_selected_capabilities(
            [{"capability_id": capability["id"], "kind": "skill", "runtime_overrides": {}}]
        )
        assert len(resolved) == 1
        assert resolved[0]["mount_type"] == "prompt"
        assert "send email safely" in (resolved[0]["prompt_fragment"] or "")
        assert "user confirmation" in (resolved[0]["prompt_fragment"] or "")
    finally:
        await db_module.close_db()
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_index_page_allows_lazy_session_creation_from_send():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="user-input"' in html
    assert 'id="user-input" placeholder="Type your message... ( /skills, /skill <slug> <task> )"\n                   onkeydown="handleUserInputKeydown(event)"' in html
    assert 'id="send-btn">Send</button>' in html
    assert 'id="slash-menu" class="slash-menu"' in html
    assert "setupSlashAutocomplete()" in html
    assert "page_size=100&sort_by=name&sort_order=asc" in html
    assert "const filtered = skills.filter((s) => {" in html
    assert "invokeToken" in html
    assert "handleUserInputKeydown(event)" in html
    assert "if (!currentSessionId) {" in html
    assert "const session = await createSession();" in html


def test_index_page_binding_switch_resets_to_new_chat_context():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "addEventListener('change', onBindingChange)" in html
    assert "Switching Binding starts a new chat context. Continue?" in html
    assert "if (!bindingId) {" in html
    assert "payload.model_key = DEFAULT_MODEL;" in html
    assert "currentSessionId = null;" in html
    assert "Send a message to start a new chat with this binding." in html


def test_index_page_default_binding_label_uses_default_llm_config(tmp_path):
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
                    "provider": "openai",
                    "name": "OpenAI Default",
                    "default_model": "gpt-5.4-mini",
                    "is_default": True,
                },
            )
            assert create_resp.status_code == 201

            response = client.get("/")

        assert response.status_code == 200
        assert "Default (openai:gpt-5.4-mini)" in response.text
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_capabilities_category_buttons_render_clickable_onclick():
    with TestClient(app) as client:
        response = client.get("/capabilities")

    assert response.status_code == 200
    html = response.text
    assert 'onclick=\'selectCategory("memory")\'' in html
    assert 'onclick="selectCategory("memory")"' not in html
    assert "Sync Superpowers" in html
    assert "syncSuperpowersSkills()" in html


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
        names = [
            item["name"]
            for item in response.json()["items"]
            if not str(item["id"]).startswith("builtin:") and item.get("kind") == "tool"
        ]
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


def test_builtin_code_run_healthcheck_works():
    with TestClient(app) as client:
        response = client.post("/api/capabilities/builtin:code-run/healthcheck")
    assert response.status_code == 200
    payload = response.json()
    assert payload["capability_id"] == "builtin:code-run"
    assert payload["status"] == "ok"


def test_builtin_atomic_tools_healthcheck_all_ok():
    expected_slugs = {
        "ask-user",
        "calculator",
        "code-run",
        "file-patch",
        "file-read",
        "file-write",
        "http-fetch",
        "start-long-term-update",
        "update-working-checkpoint",
        "web-execute-js",
        "web-scan",
    }

    with TestClient(app) as client:
        listed = client.get("/api/capabilities?page_size=100")
        assert listed.status_code == 200
        items = listed.json()["items"]
        builtin_tools = [
            item for item in items
            if str(item.get("id", "")).startswith("builtin:") and item.get("kind") == "tool"
        ]
        slugs = {item.get("slug") for item in builtin_tools}
        assert expected_slugs <= slugs

        for item in builtin_tools:
            response = client.post(f"/api/capabilities/{item['id']}/healthcheck")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"


def test_edit_user_message_truncates_following_messages(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"model_key": "openai:gpt-4.1"})
            assert create_resp.status_code == 201
            session_id = create_resp.json()["id"]

            m1 = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "user", "content": "first"},
            ).json()
            client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "assistant", "content": "first-reply"},
            )
            client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "user", "content": "second"},
            )
            client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "assistant", "content": "second-reply"},
            )

            edit_resp = client.put(
                f"/api/sessions/{session_id}/messages/{m1['id']}",
                json={"content": "first-edited"},
            )
            assert edit_resp.status_code == 200
            payload = edit_resp.json()
            assert payload["updated_message"]["content"] == "first-edited"
            assert payload["deleted_following_count"] == 3

            list_resp = client.get(f"/api/sessions/{session_id}/messages")
            assert list_resp.status_code == 200
            items = list_resp.json()
            assert len(items) == 1
            assert items[0]["role"] == "user"
            assert items[0]["content"] == "first-edited"
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_delete_user_message_truncates_following_messages(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"model_key": "openai:gpt-4.1"})
            assert create_resp.status_code == 201
            session_id = create_resp.json()["id"]

            m1 = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "user", "content": "first"},
            ).json()
            client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "assistant", "content": "first-reply"},
            )
            client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "user", "content": "second"},
            )
            client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "assistant", "content": "second-reply"},
            )

            delete_resp = client.delete(f"/api/sessions/{session_id}/messages/{m1['id']}")
            assert delete_resp.status_code == 204

            list_resp = client.get(f"/api/sessions/{session_id}/messages")
            assert list_resp.status_code == 200
            items = list_resp.json()
            assert len(items) == 0
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None


def test_delete_assistant_message_keeps_other_messages(tmp_path):
    db_path = tmp_path / "app.db"
    original_path = db_module.settings.app_db_path
    db_module._db = None
    db_module.settings.app_db_path = str(db_path)

    try:
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"model_key": "openai:gpt-4.1"})
            assert create_resp.status_code == 201
            session_id = create_resp.json()["id"]

            m1 = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "user", "content": "first"},
            ).json()
            m2 = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "assistant", "content": "first-reply"},
            ).json()
            m3 = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"role": "user", "content": "second"},
            ).json()

            delete_resp = client.delete(f"/api/sessions/{session_id}/messages/{m2['id']}")
            assert delete_resp.status_code == 204

            list_resp = client.get(f"/api/sessions/{session_id}/messages")
            assert list_resp.status_code == 200
            items = list_resp.json()
            assert [item["id"] for item in items] == [m1["id"], m3["id"]]
    finally:
        asyncio.run(db_module.close_db())
        db_module.settings.app_db_path = original_path
        db_module._db = None
