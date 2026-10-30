from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_BACKEND_ENV = _BACKEND_DIR / ".env"


def normalize_async_database_url(url: str) -> str:
    """Ensure PostgreSQL URLs use the asyncpg driver used by this service.

    Supabase's dashboard supplies standard ``postgresql://`` URLs. SQLAlchemy's
    async engine requires an async driver, so normalize common PostgreSQL URL
    schemes before passing them to ``create_async_engine`` or Alembic.
    """
    value = url.strip()
    scheme, separator, remainder = value.partition("://")
    if not separator:
        return value

    if scheme.lower() in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        return f"postgresql+asyncpg://{remainder}"
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_BACKEND_ENV, ".env") if _BACKEND_ENV.is_file() else ".env",
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

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_mode(cls, value: Any) -> Any:
        """Accept common environment labels without treating them as booleans."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "false", "0", "no", "off"}:
                return False
            if normalized in {"development", "dev", "debug", "true", "1", "yes", "on"}:
                return True
        return value

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
        # Render assigns each web service an exact public hostname. Trust that
        # hostname in addition to any explicitly configured hosts so the
        # TrustedHostMiddleware accepts Render's forwarded Host header without
        # opening the allowlist to every onrender.com subdomain.
        render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().lower().rstrip(".")
        if render_hostname and render_hostname not in self.trusted_hosts:
            self.trusted_hosts = [*self.trusted_hosts, render_hostname]

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
    # DIRECT_DATABASE_URL — URL used by Alembic migrations. This project uses
    #                     asyncpg for database connections; standard Supabase
    #                     postgresql:// URLs are normalized to asyncpg.
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
    supabase_jwt_algorithm: str = Field(default="ES256")
    supabase_jwt_audience: str = Field(default="authenticated")
    supabase_jwt_issuer: str | None = Field(default=None)
    supabase_jwks_url: str | None = Field(default=None)
    supabase_jwt_clock_skew_seconds: int = Field(default=60, ge=0, le=300)

    @field_validator("supabase_jwt_issuer", mode="before")
    @classmethod
    def normalize_jwt_issuer(cls, value: Any) -> str | None:
        if isinstance(value, str):
            trimmed = value.strip().rstrip("/")
            return trimmed if trimmed else None
        return value

    @field_validator("supabase_jwt_algorithm", mode="before")
    @classmethod
    def normalize_jwt_algorithm(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
        return "ES256"

    # ------------------------------------------------------------------ #
    # GitHub Integration (Phase 7)
    # ------------------------------------------------------------------ #
    github_client_id: str = Field(default="")
    github_client_secret: SecretStr = Field(default=SecretStr(""))
    github_oauth_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/v1/github/callback"
    )
    github_api_base_url: str = Field(default="https://api.github.com")

    @field_validator("github_client_id", mode="before")
    @classmethod
    def normalize_github_client_id(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip().strip("'\"").strip()
        return ""

    @field_validator("github_client_secret", mode="before")
    @classmethod
    def normalize_github_client_secret(cls, value: Any) -> SecretStr:
        if isinstance(value, SecretStr):
            val = value.get_secret_value().strip().strip("'\"").strip()
            return SecretStr(val)
        if isinstance(value, str):
            return SecretStr(value.strip().strip("'\"").strip())
        return SecretStr("")

    @field_validator("github_oauth_redirect_uri", mode="before")
    @classmethod
    def normalize_github_oauth_redirect_uri(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            val = value.strip().strip("'\"").strip()
            if val.endswith("/") and not val.endswith("://"):
                val = val.rstrip("/")
            return val
        return "http://localhost:8000/api/v1/github/callback"

    # ------------------------------------------------------------------ #
    # LLM reasoning — Phase 13 (opt-in; never initialized during startup)
    # ------------------------------------------------------------------ #
    llm_enabled: bool = Field(default=False)
    nebius_api_key: SecretStr = Field(default=SecretStr(""))
    nebius_base_url: str = Field(default="https://api.studio.nebius.ai/v1")
    nebius_model: str = Field(default="nvidia/Nemotron-3_5-Lightning")
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_max_attempts: int = Field(default=2, ge=1, le=3)
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=5)
    llm_max_input_tokens: int = Field(default=12_000, ge=1, le=32_000)
    llm_max_output_tokens: int = Field(default=2_500, ge=1, le=4_000)
    llm_budget_usd: float = Field(default=25.0, gt=0, le=25.0)
    llm_budget_ledger_path: str = Field(
        default=".devdoc-llm-budget.sqlite3",
        min_length=1,
    )
    llm_input_cost_per_million_usd: float = Field(default=0.0, ge=0)
    llm_output_cost_per_million_usd: float = Field(default=0.0, ge=0)
    llm_cache_ttl_seconds: int = Field(default=900, ge=0, le=86_400)
    llm_cache_max_entries: int = Field(default=128, ge=0, le=10_000)

    @field_validator("nebius_model", mode="before")
    @classmethod
    def normalize_nebius_model(cls, value: Any) -> str:
        if isinstance(value, str):
            val = value.strip()
            if "llama-3.1-nemotron-70b" in val.lower() or "nemotron-70b" in val.lower():
                return "nvidia/Nemotron-3_5-Lightning"
            return val if val else "nvidia/Nemotron-3_5-Lightning"
        return "nvidia/Nemotron-3_5-Lightning"


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
    # Observability & Telemetry (Phase 21)
    # ------------------------------------------------------------------ #
    metrics_enabled: bool = Field(default=True)
    metrics_path: str = Field(default="/metrics")
    opentelemetry_enabled: bool = Field(default=False)
    otlp_endpoint: str | None = Field(default=None)

    # ------------------------------------------------------------------ #
    # Database Read Replica (Phase 24)
    # ------------------------------------------------------------------ #
    database_replica_url: str | None = Field(default=None)

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
