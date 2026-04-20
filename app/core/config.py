from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_mode: str = "lite"  # demo | lite
    app_db_path: str = "data/app.db"
    checkpoint_db_path: str = "data/checkpoints.db"
    host: str = "0.0.0.0"
    port: int = 12138
    root_path: str = ""
    debug: bool = True
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4.1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def data_dir(self) -> Path:
        return Path("data")

    @property
    def marketplace_dir(self) -> Path:
        return self.data_dir / "marketplace"

    @property
    def use_memory_checkpoint(self) -> bool:
        return self.app_mode == "demo"


settings = Settings()
