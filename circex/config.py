from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    data_dir: Path = Field(default=Path("./data"), alias="CIRCEX_DATA_DIR")
    db_path: Path = Field(default=Path("./data/circex.sqlite"), alias="CIRCEX_DB_PATH")
    max_usd_per_run: float = Field(default=10.0, alias="CIRCEX_MAX_USD_PER_RUN")


def get_settings() -> Settings:
    return Settings()
