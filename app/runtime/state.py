from typing import Any, TypedDict


class AgentState(TypedDict):
    thread_id: str
    session_id: str
    binding_id: str | None
    model_key: str | None
    messages: list[dict[str, Any]]
    selected_capabilities: list[dict[str, Any]]
    available_tools: list[Any]
    max_steps: int
    current_step: int
    final_output: str | None
    error: str | None
