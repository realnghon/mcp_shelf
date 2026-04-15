from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_mode: str = "lite"  # demo | lite
    app_db_path: str = "data/app.db"
    checkpoint_db_path: str = "data/checkpoints.db"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    openai_api_key: str = ""
    anthropic_api_key: str = ""

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
