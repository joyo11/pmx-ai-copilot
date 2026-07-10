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

    # Clerk (M0.4). Issuer is required in prod; audience is optional.
    # Example issuer: https://curious-crab-42.clerk.accounts.dev
    clerk_jwt_issuer: str | None = None
    clerk_jwt_audience: str | None = None

    # Observability
    logfire_token: str | None = None
    logfire_send_to_logfire: bool = False  # opt-in in prod

    # LLM (M1). Keys read from env; leave commented in .env.example.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # M1 chat + retrieval knobs. Model IDs default to what §9 pins down; adjust
    # via env if Anthropic/OpenAI relabel a checkpoint.
    chat_model: str = "claude-sonnet-4-6"
    embedding_model: str = "text-embedding-3-large"
    retrieval_top_k: int = 8

    # Local disk storage for M1. R2 lands in M2 (see DESIGN §10 + DR-002).
    # Relative paths are resolved against the API package's working directory.
    storage_dir: str = "storage"

    # R2 (M2 — kept here so M2 doesn't need another config PR).
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
