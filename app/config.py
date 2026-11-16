"""Application settings, loaded from the environment only."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-key-change-me-before-deploying-please"


class Settings(BaseSettings):
    """Every knob the app has. Nothing here is hardcoded anywhere else."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    app_env: str = "development"
    secret_key: str = DEV_SECRET
    access_token_expire_minutes: int = 60 * 24 * 7

    # Database
    database_url: str = "sqlite:///./tahqeeq.db"
    sql_echo: bool = False

    # Security
    bcrypt_rounds: int = 12
    cors_origins: str = "*"
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # URL ingestion
    allow_url_fetch: bool = True
    url_fetch_max_bytes: int = 2_000_000
    url_fetch_timeout_seconds: int = 10
    url_fetch_max_redirects: int = 3

    # Analysis limits
    max_text_chars: int = 40_000
    min_text_chars: int = 80

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    enable_docs: bool = True

    @field_validator("app_env")
    @classmethod
    def _normalise_env(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        """Docs are never exposed in production, whatever the flag says."""
        return self.enable_docs and not self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def validate_for_runtime(self) -> None:
        """Fail loudly rather than run production on a development key."""
        if self.is_production and self.secret_key == DEV_SECRET:
            raise RuntimeError(
                "SECRET_KEY is still the development default. "
                "Set a real key before running with APP_ENV=production."
            )
        if self.is_production and len(self.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters in production.")
        if self.min_text_chars >= self.max_text_chars:
            raise RuntimeError("MIN_TEXT_CHARS must be smaller than MAX_TEXT_CHARS.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
