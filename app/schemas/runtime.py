from typing import Any

from pydantic import BaseModel


class RuntimeEvent(BaseModel):
    """SSE event from the runtime."""
    event_type: str  # token | tool_call | tool_result | done | error
    data: dict[str, Any] = {}
