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


def test_ops_page_exists():
    with TestClient(app) as client:
        response = client.get("/ops")
    assert response.status_code == 200
    assert "Operations" in response.text


def test_capabilities_new_page_shows_mcp_guided_form():
    with TestClient(app) as client:
        response = client.get("/capabilities/new")

    assert response.status_code == 200
    html = response.text
    assert "MCP Setup Guide" in html
    assert "Use stdio example" in html
    assert "Use streamable HTTP example" in html
    assert "Advanced Settings" in html


def test_index_page_allows_lazy_session_creation_from_send():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="user-input"' in html
    assert 'id="user-input" placeholder="Type your message..."\n                   onkeydown="if(event.key===\'Enter\'&&!event.shiftKey)sendMessage()"' in html
    assert 'id="send-btn">Send</button>' in html
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
