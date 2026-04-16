from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Capability Create/Update ---

class CapabilityCreate(BaseModel):
    kind: str = Field(..., pattern=r"^(mcp|tool|skill)$")
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    visibility: str = "public"
    owner_id: str | None = None
    type: Literal["tool", "resource", "workflow", "prompt"] = "tool"
    source_type: Literal["builtin", "plugin", "mcp_server", "custom"] = "custom"
    source_id: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    connection_config: dict[str, Any] = Field(default_factory=dict)
    schema_status: str | None = None
    last_test_status: str | None = None
    last_tested_at: str | None = None
    last_latency_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    version: str | None = None
    visibility: str | None = None
    status: str | None = None
    type: Literal["tool", "resource", "workflow", "prompt"] | None = None
    source_type: Literal["builtin", "plugin", "mcp_server", "custom"] | None = None
    source_id: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None
    connection_config: dict[str, Any] | None = None
    schema_status: str | None = None
    last_test_status: str | None = None
    last_tested_at: str | None = None
    last_latency_ms: int | None = None
    metadata: dict[str, Any] | None = None


# --- Capability Response ---

class CapabilityOut(BaseModel):
    id: str
    kind: str
    name: str
    slug: str
    description: str | None
    category: str | None
    tags: list[str]
    version: str
    visibility: str
    status: str
    owner_id: str | None
    type: Literal["tool", "resource", "workflow", "prompt"]
    source_type: Literal["builtin", "plugin", "mcp_server", "custom"]
    source_id: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any]
    connection_config: dict[str, Any]
    schema_status: str | None
    last_test_status: str | None
    last_tested_at: str | None
    last_latency_ms: int | None
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


# --- Capability Version ---

class CapabilityVersionCreate(BaseModel):
    changelog: str | None = None


class CapabilityVersionOut(BaseModel):
    id: str
    capability_id: str
    version: str
    snapshot: dict[str, Any]
    changelog: str | None
    created_at: str
