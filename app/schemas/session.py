from typing import Any

from pydantic import BaseModel, Field


# --- Session Create ---

class SessionCreate(BaseModel):
    binding_id: str | None = None
    title: str | None = None
    actor_id: str | None = None
    model_key: str | None = None
    runtime_config: dict[str, Any] = Field(default_factory=dict)


# --- Session Response ---

class SessionOut(BaseModel):
    id: str
    thread_id: str
    binding_id: str | None
    title: str | None
    actor_id: str | None
    session_status: str
    model_key: str
    runtime_config: dict[str, Any]
    last_error: str | None
    created_at: str
    updated_at: str


# --- Message Create ---

class MessageCreate(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|tool|system)$")
    content: str | None = None
    tool_event_type: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: Any = None
    tool_result: Any = None


class MessageUpdate(BaseModel):
    content: str = Field(min_length=1)


# --- Message Response ---

class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str | None
    tool_event_type: str | None
    tool_name: str | None
    tool_call_id: str | None
    tool_args: str | None
    tool_result: str | None
    message_index: int
    created_at: str


# --- Runtime ---

class RunRequest(BaseModel):
    """Trigger agent execution with the latest user message."""
    pass


class TraceEntry(BaseModel):
    node: str
    data: dict[str, Any]
    timestamp: str
