import pytest
from langchain_core.messages import AIMessage

import app.services.agent_service as agent_service_module
from app.services.agent_service import AgentService


@pytest.mark.asyncio
async def test_run_streaming_loop_falls_back_to_ainvoke_when_stream_has_no_chunks(monkeypatch):
    class DummyModel:
        async def astream(self, _messages):
            raise ValueError("No generation chunks were returned")
            yield  # pragma: no cover

        async def ainvoke(self, _messages):
            return AIMessage(content="fallback-response")

    class FakeSessionService:
        def __init__(self):
            self.saved_messages = []

        async def add_message(self, _session_id, message):
            self.saved_messages.append(message)
            return {"id": "msg_1"}

    async def fake_prepare_session_runtime(initial_state):
        return {
            **initial_state,
            "available_tools": [],
            "current_step": 0,
            "max_steps": 8,
            "error": None,
        }

    async def fake_get_chat_model(binding_id=None, model_key_override=None):  # noqa: ARG001
        return DummyModel()

    monkeypatch.setattr(agent_service_module, "prepare_session_runtime", fake_prepare_session_runtime)
    monkeypatch.setattr(agent_service_module, "get_chat_model", fake_get_chat_model)

    service = AgentService()
    fake_session_service = FakeSessionService()
    service.session_service = fake_session_service

    initial_state = {
        "thread_id": "th_1",
        "session_id": "sess_1",
        "binding_id": None,
        "model_key": "openai:gpt-4.1",
        "messages": [{"role": "user", "content": "hello"}],
        "selected_capabilities": [],
        "available_tools": [],
        "max_steps": 8,
        "current_step": 0,
        "final_output": None,
        "error": None,
    }

    events = []
    async for event in service._run_streaming_loop("sess_1", initial_state):
        events.append(event)

    assert any(ev.event_type == "token" for ev in events)
    assert events[-1].event_type == "done"
    assert events[-1].data["content"] == "fallback-response"

    assert len(fake_session_service.saved_messages) == 1
    assert fake_session_service.saved_messages[0].content == "fallback-response"


@pytest.mark.asyncio
async def test_run_streaming_loop_persists_tool_call_and_skips_empty_assistant(monkeypatch):
    class DummyModel:
        def __init__(self):
            self._step = 0

        async def astream(self, _messages):
            if self._step == 0:
                self._step += 1
                yield AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "tc_1", "name": "calculator", "args": {"expression": "1+1"}},
                    ],
                )
                return
            yield AIMessage(content="final-answer")

    class FakeSessionService:
        def __init__(self):
            self.saved_messages = []

        async def add_message(self, _session_id, message):
            self.saved_messages.append(message)
            return {"id": f"msg_{len(self.saved_messages)}"}

    async def fake_prepare_session_runtime(initial_state):
        return {
            **initial_state,
            "available_tools": [],
            "current_step": 0,
            "max_steps": 8,
            "error": None,
        }

    async def fake_get_chat_model(binding_id=None, model_key_override=None):  # noqa: ARG001
        return model

    async def fake_execute_tool_node(state):
        msgs = list(state.get("messages", []))
        msgs.append(
            {
                "role": "tool",
                "content": "2",
                "tool_name": "calculator",
                "tool_call_id": "tc_1",
                "tool_args": {"expression": "1+1"},
                "tool_result": "2",
            }
        )
        return {"messages": msgs, "error": None}

    model = DummyModel()
    monkeypatch.setattr(agent_service_module, "prepare_session_runtime", fake_prepare_session_runtime)
    monkeypatch.setattr(agent_service_module, "get_chat_model", fake_get_chat_model)
    monkeypatch.setattr(agent_service_module, "execute_tool_node", fake_execute_tool_node)

    service = AgentService()
    fake_session_service = FakeSessionService()
    service.session_service = fake_session_service

    initial_state = {
        "thread_id": "th_1",
        "session_id": "sess_1",
        "binding_id": None,
        "model_key": "openai:gpt-4.1",
        "messages": [{"role": "user", "content": "calc 1+1"}],
        "selected_capabilities": [],
        "available_tools": [],
        "max_steps": 8,
        "current_step": 0,
        "final_output": None,
        "error": None,
    }

    events = []
    async for event in service._run_streaming_loop("sess_1", initial_state):
        events.append(event)

    event_types = [ev.event_type for ev in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert events[-1].event_type == "done"
    assert events[-1].data["content"] == "final-answer"

    assert len(fake_session_service.saved_messages) == 3
    first, second, third = fake_session_service.saved_messages
    assert first.role == "tool"
    assert first.tool_event_type == "call"
    assert first.tool_name == "calculator"
    assert first.tool_call_id == "tc_1"
    assert first.tool_result is None
    assert second.role == "tool"
    assert second.tool_event_type == "result"
    assert second.tool_result == "2"
    assert third.role == "assistant"
    assert third.content == "final-answer"


@pytest.mark.asyncio
async def test_resolve_slash_command_lists_skills():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return (
                [
                    {"id": "cap_1", "slug": "s1", "name": "Skill One"},
                    {"id": "cap_2", "slug": "s2", "name": "Skill Two"},
                ],
                2,
            )

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    messages = [{"role": "user", "content": "/skills"}]
    result = await service._resolve_slash_command(messages)
    assert result is not None
    assert result["mode"] == "skills_list"
    assert "可用 Skills（按分组）" in result["content"]
    assert "skills/s1 (Skill One)" in result["content"]


@pytest.mark.asyncio
async def test_resolve_slash_command_injects_ad_hoc_skill_and_rewrites_user_objective():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return (
                [
                    {"id": "cap_42", "slug": "superpowers-using-superpowers", "name": "SP"},
                ],
                1,
            )

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    messages = [{"role": "user", "content": "/skill superpowers-using-superpowers 帮我做需求澄清"}]
    result = await service._resolve_slash_command(messages)
    assert result is not None
    assert result["mode"] == "skill_invoke"
    assert result["messages"][0]["content"] == "帮我做需求澄清"
    assert result["ad_hoc_capabilities"][0]["capability_id"] == "cap_42"


@pytest.mark.asyncio
async def test_resolve_slash_command_matches_skill_by_suffix():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return (
                [
                    {"id": "cap_42", "slug": "superpowers-using-superpowers", "name": "SP"},
                ],
                1,
            )

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    messages = [{"role": "user", "content": "/skill using-superpowers 帮我建立工作流"}]
    result = await service._resolve_slash_command(messages)
    assert result is not None
    assert result["mode"] == "skill_invoke"
    assert result["ad_hoc_capabilities"][0]["capability_id"] == "cap_42"


@pytest.mark.asyncio
async def test_resolve_slash_command_pack_fallback_uses_pack_default():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return (
                [
                    {"id": "cap_a", "slug": "superpowers-brainstorming", "name": "brainstorming"},
                    {"id": "cap_b", "slug": "superpowers-using-superpowers", "name": "using-superpowers"},
                ],
                2,
            )

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    messages = [{"role": "user", "content": "/skill superpowers/ 帮我开始工作流"}]
    result = await service._resolve_slash_command(messages)
    assert result is not None
    assert result["mode"] == "skill_invoke"
    assert result["ad_hoc_capabilities"][0]["capability_id"] == "cap_b"


@pytest.mark.asyncio
async def test_build_skill_catalog_prompt_contains_available_skills():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return (
                [
                    {"id": "cap_1", "slug": "superpowers-writing-plans", "name": "writing-plans", "description": "plan skill"},
                    {"id": "cap_2", "slug": "superpowers-test-driven-development", "name": "tdd", "description": "tdd skill"},
                ],
                2,
            )

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    prompt = await service._build_skill_catalog_prompt(ttl_seconds=0)
    assert prompt is not None
    assert "Available skills:" in prompt
    assert "superpowers-writing-plans" in prompt
    assert "superpowers-test-driven-development" in prompt


@pytest.mark.asyncio
async def test_resolve_auto_skill_for_message_matches_plan_keyword():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return (
                [
                    {"id": "cap_plan", "slug": "superpowers-writing-plans", "name": "writing-plans", "description": "write plans"},
                    {"id": "cap_tdd", "slug": "superpowers-test-driven-development", "name": "tdd", "description": "test first"},
                ],
                2,
            )

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    auto = await service._resolve_auto_skill_for_message(
        [{"role": "user", "content": "请帮我先做一个详细的实施计划"}]
    )
    assert auto is not None
    assert auto["capability_id"] == "cap_plan"


@pytest.mark.asyncio
async def test_resolve_auto_skill_for_message_skips_skill_listing_question():
    class FakeCapabilityRepo:
        async def list_all(self, **kwargs):  # noqa: ARG002
            return ([{"id": "cap_1", "slug": "superpowers-writing-plans", "name": "writing-plans", "description": ""}], 1)

    service = AgentService()
    service.capability_repo = FakeCapabilityRepo()
    auto = await service._resolve_auto_skill_for_message(
        [{"role": "user", "content": "你有哪些skill"}]
    )
    assert auto is None
