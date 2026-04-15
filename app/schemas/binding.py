from typing import Any

from pydantic import BaseModel, Field


# --- Binding Create/Update ---

class BindingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    model_key: str = Field(..., min_length=1)
    system_prompt: str | None = None
    max_steps: int = 8
    temperature: float | None = None
    allow_shell: bool = False
    owner_id: str | None = None
    visibility: str = "private"


class BindingUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    model_key: str | None = None
    system_prompt: str | None = None
    max_steps: int | None = None
    temperature: float | None = None
    allow_shell: bool | None = None
    visibility: str | None = None


# --- Binding Capability ---

class BindingCapabilityAdd(BaseModel):
    capability_id: str
    is_enabled: bool = True
    mount_order: int = 0
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)


class BindingCapabilityOut(BaseModel):
    id: str
    binding_id: str
    capability_id: str
    is_enabled: bool
    mount_order: int
    runtime_overrides: dict[str, Any]
    # joined fields
    capability_name: str | None = None
    capability_kind: str | None = None
    capability_slug: str | None = None


# --- Binding Response ---

class BindingOut(BaseModel):
    id: str
    name: str
    description: str | None
    model_key: str
    system_prompt: str | None
    max_steps: int
    temperature: float | None
    allow_shell: bool
    owner_id: str | None
    visibility: str
    created_at: str
    updated_at: str
    capabilities: list[BindingCapabilityOut] = Field(default_factory=list)
