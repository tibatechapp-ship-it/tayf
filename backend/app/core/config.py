"""Typed application settings.

Every value comes from the environment (or the repo-root ``.env``).
No secret ever lives in source code.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "visionforge-backend"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    # Dev-only origins: the Vite dev server. Production values come from .env.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (re-read on process restart)."""
    return Settings()
