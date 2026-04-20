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

    @staticmethod
    def _mask_api_key(config: dict | None) -> dict | None:
        if not config:
            return config
        sanitized = dict(config)
        sanitized["api_key_set"] = bool(sanitized.get("api_key"))
        sanitized.pop("api_key", None)
        return sanitized

    async def list_configs(self) -> list[dict]:
        configs = await self.repo.list_all()
        return [self._mask_api_key(c) for c in configs if c is not None]

    async def get_config(self, config_id: str) -> dict | None:
        config = await self.repo.get_by_id(config_id)
        return self._mask_api_key(config)

    async def create_config(self, data: LLMConfigCreate) -> dict:
        created = await self.repo.create(data.model_dump())
        masked = self._mask_api_key(created)
        return masked or {}

    async def update_config(self, config_id: str, data: LLMConfigUpdate) -> dict | None:
        update_data = data.model_dump(exclude_none=True)
        updated = await self.repo.update(config_id, update_data)
        return self._mask_api_key(updated)

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
        """Resolve base URL: DB first, then .env fallback."""
        config = await self.repo.get_by_provider(provider)
        if config and config.get("base_url"):
            return config["base_url"]

        # Fallback to .env
        if provider == "openai":
            return settings.openai_base_url or None
        elif provider == "anthropic":
            return settings.anthropic_base_url or None
        return None

    async def resolve_default_model_key(self) -> str:
        """Resolve effective default provider/model key for new sessions."""
        default_cfg = await self.repo.get_default()
        if default_cfg:
            provider = str(default_cfg.get("provider") or "openai").strip() or "openai"
            default_model = str(default_cfg.get("default_model") or "").strip()
            if default_model:
                return f"{provider}:{default_model}"

        openai_model = (settings.openai_model or "").strip() or "gpt-4.1"
        return f"openai:{openai_model}"
