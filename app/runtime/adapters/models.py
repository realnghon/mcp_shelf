"""Model adapter - resolves LLM config from DB first, then .env fallback."""

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.repositories.binding_repo import BindingRepo
from app.repositories.llm_config_repo import LLMConfigRepo

_model_cache: dict = {}


async def get_chat_model(
    binding_id: str | None = None,
    model_key_override: str | None = None,
) -> object:
    """Get a chat model instance, resolving config from DB -> .env."""
    repo = LLMConfigRepo()
    # Default model from .env settings
    model_key = f"openai:{settings.openai_model}"
    temperature = 0.7

    if model_key_override:
        model_key = model_key_override

    if binding_id:
        bind_repo = BindingRepo()
        binding = await bind_repo.get_by_id(binding_id)
        if binding:
            model_key = binding["model_key"]
            if binding.get("temperature") is not None:
                temperature = binding["temperature"]

    provider, model_name = model_key.split(":", 1) if ":" in model_key else ("openai", model_key)

    # Resolve API key: DB first, .env fallback
    api_key = None
    base_url = None

    db_config = await repo.get_by_provider(provider)
    if db_config:
        api_key = db_config.get("api_key")
        base_url = db_config.get("base_url")
        if db_config.get("default_model") and not binding_id:
            model_name = db_config["default_model"]

    # Fallback to .env
    if not api_key:
        if provider == "openai":
            api_key = settings.openai_api_key or None
        elif provider == "anthropic":
            api_key = settings.anthropic_api_key or None

    # Fallback base_url to .env
    if not base_url:
        if provider == "openai":
            base_url = settings.openai_base_url or None
        elif provider == "anthropic":
            base_url = settings.anthropic_base_url or None
    base_url = _normalize_base_url(provider, base_url)

    cache_key = f"{provider}:{model_name}:{temperature}:{base_url or 'default'}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    if provider == "openai":
        kwargs = {"model": model_name, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        model = ChatOpenAI(**kwargs)
    elif provider == "anthropic":
        kwargs = {"model": model_name, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        model = ChatAnthropic(**kwargs)
    else:
        kwargs = {"model": model_name, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        model = ChatOpenAI(**kwargs)

    _model_cache[cache_key] = model
    return model


def _normalize_base_url(provider: str, base_url: str | None) -> str | None:
    if not base_url:
        return base_url
    if provider != "openai":
        return base_url
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"
