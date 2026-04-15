"""Model adapter - resolves LLM config from DB first, then .env fallback."""

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.repositories.llm_config_repo import LLMConfigRepo
from app.repositories.binding_repo import BindingRepo
from app.core.config import settings

_model_cache: dict = {}


async def get_chat_model(binding_id: str | None = None) -> object:
    """Get a chat model instance, resolving config from DB -> .env."""
    repo = LLMConfigRepo()
    model_key = "openai:gpt-4.1"  # default
    temperature = 0.7

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
        if db_config.get("default_model") and model_name == model_key:
            model_name = db_config["default_model"]

    # Fallback to .env
    if not api_key:
        if provider == "openai":
            api_key = settings.openai_api_key or None
        elif provider == "anthropic":
            api_key = settings.anthropic_api_key or None

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
