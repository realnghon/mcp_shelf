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
