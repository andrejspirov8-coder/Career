"""Typed application configuration management."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central typed settings loaded from environment or defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "career-job-search"
    environment: str = "development"
    debug: bool = False
    network_timeout_seconds: int = Field(default=20, ge=1, le=120)
    database_path: str = "state/opportunities.db"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
