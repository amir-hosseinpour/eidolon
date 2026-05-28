from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EIDOLON_",
        env_file=".env",
        extra="ignore",
    )

    debug: bool = False
    hmac_secret: str = Field(
        default="dev-only-change-me-minimum-32-bytes!!",
        description="Signing key for scope tokens. Override in production.",
    )
    scope_token_ttl_seconds: int = 8 * 60 * 60
    litellm_url: str = "http://127.0.0.1:4000"
    database_url: str = "sqlite+aiosqlite:///./eidolon.db"
    orchestrator_bind: str = "127.0.0.1:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
