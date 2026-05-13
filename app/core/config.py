"""Application settings — typed + validated via Pydantic."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed config. All values come from `.env` or OS env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = True
    app_secret_key: str = Field("change-me-to-64-random-chars", min_length=16)
    app_base_url: str = "http://localhost:8000"
    app_cors_origins: str = "http://localhost"

    # ─── Database ─────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://pi:pi@localhost:5432/pi_backend"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    @field_validator("database_url", mode="after")
    @classmethod
    def _coerce_async_driver(cls, v: str) -> str:
        """Normalize DATABASE_URL for asyncpg.

        Common hosting providers (Neon, Supabase, Railway, Heroku) hand out
        DATABASE_URL in a psycopg2-friendly shape:
            postgresql://user:pass@host/db?sslmode=require&channel_binding=require
        asyncpg uses a different parameter set and crashes on these query
        flags. We:
          1. Upgrade the scheme to `postgresql+asyncpg://` so SQLAlchemy
             picks the async driver.
          2. Drop libpq-only flags asyncpg doesn't understand
             (`sslmode`, `channel_binding`).
          3. Translate `sslmode=require` → `ssl=true` so TLS still happens
             on hosts that require it (Neon, Supabase, Railway managed PG).
        """
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

        # Step 1: scheme normalize
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgres://"):  # legacy Heroku
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)

        # Step 2 & 3: scrub libpq-only query params
        parts = urlsplit(v)
        if not parts.query:
            return v
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        sslmode = params.pop("sslmode", None)
        params.pop("channel_binding", None)  # asyncpg ignores; libpq-only
        if sslmode in {"require", "verify-ca", "verify-full"} and "ssl" not in params:
            params["ssl"] = "true"
        new_query = urlencode(params)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    # ─── Redis / Celery ───────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ─── JWT ──────────────────────────────────────────────
    jwt_secret: str = Field("change-me-to-64-random-chars", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days
    tenant_jwt_expire_minutes: int = 15

    # ─── License ──────────────────────────────────────────
    license_key_prefix: str = "pi_"
    license_default_tier: Literal["free", "pro", "max", "enterprise"] = "free"
    tenant_license_key_pattern: str = r"^[A-Z0-9]{4,8}-[A-Z0-9]{5,8}-[A-Z0-9]{5}-[A-Z0-9]{5}$"

    # ─── Google APIs (PageSpeed, Indexing) ────────────────
    google_psi_api_key: str = ""  # public free tier: 25K/day without key
    google_indexing_service_account_json: str = ""  # path to JSON credential

    # ─── Rate limits (per-month quotas) ───────────────────
    rate_limit_free_per_month: int = 5_000
    rate_limit_pro_per_month: int = 100_000
    rate_limit_max_per_month: int = 500_000
    rate_limit_burst_per_minute: int = 10

    # ─── Plugin updates ───────────────────────────────────
    updates_storage_path: str = "./data/plugin-releases"
    updates_signing_key: str = "change-me"

    # ─── Logging / monitoring ─────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    sentry_dsn: str = ""

    @field_validator("app_cors_origins")
    @classmethod
    def _split_csv(cls, v: str) -> str:
        # Keep as string in settings, parsed by consumers
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.app_cors_origins.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def monthly_quota_for(self) -> dict[str, int]:
        return {
            "free": self.rate_limit_free_per_month,
            "pro": self.rate_limit_pro_per_month,
            "max": self.rate_limit_max_per_month,
            "enterprise": -1,
        }


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
