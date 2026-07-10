"""Runtime configuration, loaded from env with sane dev defaults."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(
        default="development", description="development | staging | production"
    )
    log_level: str = Field(default="INFO")

    # Frontend origin(s) allowed to talk to us. Comma-separated.
    cors_allow_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001,http://localhost:3002,https://pmx-ai-copilot.vercel.app"
    )

    # DB (populated in M0.3). Not required for M0.2.
    database_url: str | None = None

    # Observability
    logfire_token: str | None = None
    logfire_send_to_logfire: bool = False  # opt-in in prod

    # LLM (populated in M1)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Storage (populated in M1)
    r2_endpoint: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Reset via `get_settings.cache_clear()` in tests."""
    return Settings()
