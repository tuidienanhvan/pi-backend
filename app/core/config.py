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
        """Upgrade scheme to postgresql+asyncpg:// so SQLAlchemy picks the
        async driver. Query-string params (sslmode, channel_binding, ssl)
        are intentionally LEFT IN PLACE — `app.core.db._build_engine_args`
        parses them off and converts to asyncpg `connect_args` so SQLAlchemy
        never tries to pass libpq-only kwargs to asyncpg.connect().
        """
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):  # legacy Heroku style
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

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

    # ─── Email (Resend primary, SMTP fallback) ──────────────────
    # Resend.com: 3,000 emails/month free, modern API
    resend_api_key: str = ""
    email_from: str = "Pi Ecosystem <noreply@pi-ecosystem.com>"
    email_reply_to: str = ""

    # SMTP fallback (Gmail/Brevo/Mailtrap) — used when resend_api_key empty
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Frontend URLs for reset/verification email links
    frontend_store_url: str = "https://store.pi-ecosystem.com"
    frontend_dashboard_url: str = "https://app.pi-ecosystem.com"

    # ─── OAuth (Google + GitHub) ────────────────────────────
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    # Where to redirect after OAuth success (frontend handles JWT cookie)
    oauth_redirect_base: str = "https://store.pi-ecosystem.com/auth/oauth/callback"

    # ─── Rate limits ──────────────────────────────────────
    # NOTE: Per-tier monthly quotas now live in `app.saas.tiers.TIER_MATRIX`
    # (single source of truth). The `rate_limit_*_per_month` env vars are
    # DEPRECATED — kept here only so existing Railway env vars with these
    # names don't trigger a pydantic validation error on boot. Callers
    # MUST use `monthly_quota_for_tier(tier)` from `app.saas.tiers`.
    rate_limit_free_per_month: int = 50_000   # deprecated — see saas.tiers
    rate_limit_pro_per_month: int = 1_000_000  # deprecated
    rate_limit_max_per_month: int = 3_000_000  # deprecated
    rate_limit_burst_per_minute: int = 10      # still active — burst limiter

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
        """DEPRECATED — use `app.saas.tiers.monthly_quota_for_tier(tier)`.

        Kept as a proxy for any third-party callers; reads from the
        canonical TIER_MATRIX so values cannot drift.
        """
        from app.saas.tiers import TIER_MATRIX
        return {
            tier: (-1 if spec["monthly_tokens"] == -1 else spec["monthly_tokens"])
            for tier, spec in TIER_MATRIX.items()
        }


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
