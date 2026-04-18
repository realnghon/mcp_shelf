from typing import Any
from pydantic import BaseModel, Field


class LLMConfigCreate(BaseModel):
    provider: str = Field(..., pattern=r"^(openai|anthropic|custom)$")
    name: str = Field(..., min_length=1, max_length=100)
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    is_default: bool = False
    extra_config: dict[str, Any] = Field(default_factory=dict)


class LLMConfigUpdate(BaseModel):
    provider: str | None = Field(default=None, pattern=r"^(openai|anthropic|custom)$")
    name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    is_default: bool | None = None
    extra_config: dict[str, Any] | None = None


class LLMConfigOut(BaseModel):
    id: str
    provider: str
    name: str
    api_key_set: bool = False  # never expose the actual key
    base_url: str | None = None
    default_model: str | None = None
    is_default: bool = False
    extra_config: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
