from __future__ import annotations

from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    app_name: str = Field(default="DEVDOC API")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return value

    # ------------------------------------------------------------------ #
    # Database — PostgreSQL / Supabase
    #
    # DATABASE_URL      — async URL used by SQLAlchemy at runtime
    #                     format: postgresql+asyncpg://user:pass@host:port/db
    #
    # DIRECT_DATABASE_URL — non-pooled URL for Alembic migrations
    #                     format: postgresql+psycopg2://user:pass@host:port/db
    #                     (or postgresql+asyncpg:// for async migrations)
    # ------------------------------------------------------------------ #
    database_url: str = Field(default="")
    direct_database_url: str = Field(default="")

    # Connection-pool tuning
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)
    db_pool_timeout: int = Field(default=30)
    db_pool_recycle: int = Field(default=1800)
    db_echo: bool = Field(default=False)

    # ------------------------------------------------------------------ #
    # Supabase & Authentication
    #
    # SUPABASE_SERVICE_ROLE_KEY — backend-only; NEVER sent to frontend
    # SUPABASE_ANON_KEY         — safe for frontend/public use
    # SUPABASE_JWT_SECRET       — used to verify Supabase-issued JWTs
    # ------------------------------------------------------------------ #
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: SecretStr = Field(default=SecretStr(""))

    # JWT verification settings
    supabase_jwt_secret: SecretStr = Field(default=SecretStr(""))
    supabase_jwt_algorithm: str = Field(default="HS256")
    supabase_jwt_audience: str = Field(default="authenticated")
    supabase_jwt_issuer: str | None = Field(default=None)
    supabase_jwks_url: str | None = Field(default=None)

    # ------------------------------------------------------------------ #
    # GitHub Integration (Phase 7)
    # ------------------------------------------------------------------ #
    github_client_id: str = Field(default="")
    github_client_secret: SecretStr = Field(default=SecretStr(""))
    github_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/github/callback"
    )
    github_api_base_url: str = Field(default="https://api.github.com")

    # ------------------------------------------------------------------ #
    # LLM reasoning — Phase 13 (opt-in; never initialized during startup)
    # ------------------------------------------------------------------ #
    llm_enabled: bool = Field(default=False)
    nebius_api_key: SecretStr = Field(default=SecretStr(""))
    nebius_base_url: str = Field(default="https://api.studio.nebius.ai/v1")
    nebius_model: str = Field(default="nvidia/Llama-3.1-Nemotron-70B-Instruct")
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_max_attempts: int = Field(default=2, ge=1, le=3)
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=5)
    llm_max_input_tokens: int = Field(default=12_000, ge=1, le=32_000)
    llm_max_output_tokens: int = Field(default=1_000, ge=1, le=4_000)
    llm_budget_usd: float = Field(default=25.0, gt=0, le=25.0)
    llm_budget_ledger_path: str = Field(
        default=".devdoc-llm-budget.sqlite3",
        min_length=1,
    )
    llm_input_cost_per_million_usd: float = Field(default=0.0, ge=0)
    llm_output_cost_per_million_usd: float = Field(default=0.0, ge=0)
    llm_cache_ttl_seconds: int = Field(default=900, ge=0, le=86_400)
    llm_cache_max_entries: int = Field(default=128, ge=0, le=10_000)

    # ------------------------------------------------------------------ #
    # Convenience helpers
    # ------------------------------------------------------------------ #
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def database_configured(self) -> bool:
        """True when a real database URL has been provided."""
        return bool(self.database_url)

    @property
    def jwt_configured(self) -> bool:
        """True when JWT verification credentials (secret or JWKS) are configured."""
        return bool(
            self.supabase_jwt_secret.get_secret_value()
            or self.supabase_jwks_url
            or self.supabase_url
        )

    @property
    def github_configured(self) -> bool:
        """True when GitHub OAuth client credentials are configured."""
        return bool(self.github_client_id and self.github_client_secret.get_secret_value())


settings = Settings()
