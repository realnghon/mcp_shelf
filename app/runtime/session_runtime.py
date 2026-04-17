from __future__ import annotations

from app.runtime.nodes.build_tools import build_tools_node
from app.runtime.nodes.load_binding import load_binding_node
from app.runtime.state import AgentState


async def prepare_session_runtime(initial_state: AgentState) -> AgentState:
    """Prepare runtime state via phase2 assembly pipeline."""
    state: AgentState = dict(initial_state)  # type: ignore[assignment]
    state.update(await load_binding_node(state))
    state.update(await build_tools_node(state))
    return state

