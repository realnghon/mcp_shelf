"""LLM configuration service.

Resolution priority:
1. Database llm_configs (set via frontend)
2. .env file (backend fallback)
"""

from app.repositories.llm_config_repo import LLMConfigRepo
from app.core.config import settings
from app.schemas.llm_config import LLMConfigCreate, LLMConfigUpdate


class LLMConfigService:
    def __init__(self):
        self.repo = LLMConfigRepo()

    async def list_configs(self) -> list[dict]:
        configs = await self.repo.list_all()
        # Mask API keys in response
        for c in configs:
            c["api_key_set"] = bool(c.get("api_key"))
            c.pop("api_key", None)
        return configs

    async def get_config(self, config_id: str) -> dict | None:
        config = await self.repo.get_by_id(config_id)
        if config:
            config["api_key_set"] = bool(config.get("api_key"))
            config.pop("api_key", None)
        return config

    async def create_config(self, data: LLMConfigCreate) -> dict:
        return await self.repo.create(data.model_dump())

    async def update_config(self, config_id: str, data: LLMConfigUpdate) -> dict | None:
        update_data = data.model_dump(exclude_none=True)
        return await self.repo.update(config_id, update_data)

    async def delete_config(self, config_id: str) -> bool:
        return await self.repo.delete(config_id)

    async def resolve_api_key(self, provider: str) -> str | None:
        """Resolve API key: DB first, then .env fallback."""
        # Try database first
        config = await self.repo.get_by_provider(provider)
        if config and config.get("api_key"):
            return config["api_key"]

        # Fallback to .env
        if provider == "openai":
            return settings.openai_api_key or None
        elif provider == "anthropic":
            return settings.anthropic_api_key or None
        return None

    async def resolve_base_url(self, provider: str) -> str | None:
        """Resolve base URL for a provider."""
        config = await self.repo.get_by_provider(provider)
        if config and config.get("base_url"):
            return config["base_url"]
        return None
