from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    debug: bool = Field(default=False)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # ------------------------------------------------------------------ #
    # HTTP security
    # ------------------------------------------------------------------ #
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    security_headers_enabled: bool = Field(default=True)
    hsts_max_age_seconds: int = Field(default=31536000, ge=0, le=31536000)

    @field_validator("trusted_hosts", mode="before")
    @classmethod
    def parse_trusted_hosts(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [host.strip() for host in value.split(",") if host.strip()]
        elif isinstance(value, list):
            value = [str(host).strip() for host in value if str(host).strip()]
        else:
            raise ValueError("Trusted hosts must be a list or comma-separated string")

        normalized: list[str] = []
        for host in value:
            candidate = host.strip().lower()
            if not candidate:
                continue
            if candidate.startswith("."):
                raise ValueError("Trusted host entries must not start with a dot")
            normalized.append(candidate)
        return normalized

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

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
    # API rate limiting
    # ------------------------------------------------------------------ #
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_redis_url: SecretStr = Field(default=SecretStr(""))
    rate_limit_tenant_capacity: int = Field(default=120, ge=1, le=100_000)
    rate_limit_tenant_refill_per_second: float = Field(default=2.0, gt=0, le=10_000)
    rate_limit_ip_capacity: int = Field(default=120, ge=1, le=100_000)
    rate_limit_ip_refill_per_second: float = Field(default=10.0, gt=0, le=10_000)
    rate_limit_memory_max_entries: int = Field(default=10_000, ge=100, le=100_000)

    @model_validator(mode="after")
    def validate_runtime_security_defaults(self) -> Settings:
        if self.is_production and not self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must be configured when ENVIRONMENT=production")
        if self.is_production and not self.rate_limit_enabled:
            raise ValueError("API rate limiting cannot be disabled in production")
        if self.is_production and not self.rate_limit_redis_url.get_secret_value():
            raise ValueError("RATE_LIMIT_REDIS_URL must be configured when ENVIRONMENT=production")
        if not self.is_production and not self.trusted_hosts:
            self.trusted_hosts = ["localhost", "127.0.0.1", "[::1]", "testserver"]
        return self

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
    # External knowledge search — Phase 14 (disabled unless injected)
    # ------------------------------------------------------------------ #
    knowledge_search_enabled: bool = Field(default=False)
    tavily_api_key: SecretStr = Field(default=SecretStr(""))
    knowledge_search_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    knowledge_search_max_results: int = Field(default=5, ge=1, le=10)
    knowledge_search_max_query_length: int = Field(default=400, ge=64, le=1_000)
    knowledge_search_max_response_bytes: int = Field(
        default=250_000,
        ge=1_024,
        le=2_000_000,
    )
    knowledge_search_max_retries: int = Field(default=1, ge=0, le=2)
    knowledge_search_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=2)
    knowledge_search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = Field(
        default="basic"
    )
    knowledge_search_preferred_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    knowledge_search_allowed_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    knowledge_searches_per_investigation: int = Field(default=2, ge=1, le=10)
    knowledge_searches_per_request: int = Field(default=1, ge=1, le=3)
    knowledge_search_max_concurrent: int = Field(default=2, ge=1, le=10)
    knowledge_search_max_title_length: int = Field(default=512, ge=32, le=2_048)
    knowledge_search_max_content_length: int = Field(default=2_000, ge=100, le=8_000)
    knowledge_search_max_url_length: int = Field(default=2_048, ge=128, le=4_096)
    knowledge_search_cache_ttl_seconds: int = Field(default=600, ge=0, le=86_400)
    knowledge_search_cache_max_entries: int = Field(default=128, ge=0, le=10_000)
    knowledge_search_usage_window_seconds: int = Field(default=86_400, ge=60, le=604_800)
    knowledge_search_usage_max_entries: int = Field(default=10_000, ge=100, le=100_000)

    @field_validator(
        "knowledge_search_preferred_domains",
        "knowledge_search_allowed_domains",
        mode="before",
    )
    @classmethod
    def parse_knowledge_search_domains(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_domains = [domain.strip() for domain in value.split(",") if domain.strip()]
        elif isinstance(value, list):
            raw_domains = [str(domain).strip() for domain in value if str(domain).strip()]
        else:
            raise ValueError("Knowledge search domains must be a list or comma-separated string")

        normalized: list[str] = []
        for domain in raw_domains:
            candidate = domain.lower().rstrip(".")
            if (
                len(candidate) > 253
                or "://" in candidate
                or "/" in candidate
                or not re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                    candidate,
                )
            ):
                raise ValueError("Knowledge search domains must be bare DNS domain names")
            if candidate not in normalized:
                normalized.append(candidate)
            if len(normalized) > 50:
                raise ValueError("At most 50 knowledge search domains may be configured")
        return normalized

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
