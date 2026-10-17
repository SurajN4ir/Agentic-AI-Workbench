"""
app/config.py — Sovereign Workbench Configuration
==================================================
All application settings loaded from environment variables via Pydantic Settings.
The application will REFUSE TO START if JWT_SECRET_KEY or POSTGRES_PASSWORD
are not set — there are no insecure defaults for critical secrets.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration. All values sourced from environment variables.
    Required variables have no default and will raise ValidationError if absent.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Environment ────────────────────────────────────────────
    app_env: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ─── PostgreSQL ──────────────────────────────────────────────
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "sovereign_workbench"
    postgres_user: str = "sovereign"
    postgres_password: str  # REQUIRED — no default

    # ─── JWT ─────────────────────────────────────────────────────
    jwt_secret_key: str  # REQUIRED — no default; must be ≥ 32 chars
    jwt_access_token_expire_seconds: int = 28800  # 8 hours
    jwt_refresh_token_expire_seconds: int = 604800  # 7 days
    jwt_algorithm: str = "HS256"

    # ─── Ollama ──────────────────────────────────────────────────
    ollama_base_url: str = "http://127.0.0.1:11434"

    # ─── Strict-offline mode ─────────────────────────────────────
    strict_offline: bool = False

    # ─── File uploads & workspace ────────────────────────────────
    max_upload_size_bytes: int = 52_428_800  # 50 MB
    workspace_dir: str = "workspace"

    # ─── Sandbox isolation ───────────────────────────────────────
    sandbox_image: str = "python:3.11-slim"
    sandbox_mem_limit: str = "512m"
    sandbox_timeout_seconds: int = 15

    # ─── CORS ────────────────────────────────────────────────────
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ─── Rate limiting ───────────────────────────────────────────
    rate_limit_auth_per_minute: int = 10
    rate_limit_agent_per_minute: int = 30

    # ─── Account lockout ─────────────────────────────────────────
    max_failed_login_attempts: int = 5
    account_lockout_seconds: int = 900  # 15 minutes

    # ─── Derived properties ──────────────────────────────────────
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync DSN for Alembic and psycopg-pool."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # ─── Validators ──────────────────────────────────────────────
    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        # Reject the example placeholder value
        if "CHANGE_ME" in v or v == "sovereign_agent_air_gapped_jwt_secret_key_2026":
            raise ValueError(
                "JWT_SECRET_KEY is set to a known insecure placeholder value. "
                "Generate a strong secret and set it in your .env file."
            )
        return v

    @field_validator("postgres_password")
    @classmethod
    def validate_db_password(cls, v: str) -> str:
        if "CHANGE_ME" in v or v in ("postgres", "password", "postgres_sovereign_2026"):
            raise ValueError(
                "POSTGRES_PASSWORD is set to a known weak or placeholder value. "
                "Set a strong random password in your .env file."
            )
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton. Raises ValidationError on startup if required
    environment variables are missing or invalid — no silent fallbacks.
    """
    return Settings()  # type: ignore[call-arg]
