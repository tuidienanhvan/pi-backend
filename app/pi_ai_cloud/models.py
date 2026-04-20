"""Pi AI Cloud — ORM models for token economy."""

from datetime import datetime
from typing import Literal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin

# A "token" is an abstract credit unit. 1 Pi token ≈ 1 model-token (input or
# output) across providers, normalised so pricing stays predictable.

LedgerOp = Literal["topup", "spend", "refund", "bonus", "admin_adjust"]


class TokenWallet(Base, TimestampMixin):
    """Per-license token balance. One wallet per license."""

    __tablename__ = "ai_token_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    lifetime_topup: Mapped[int] = mapped_column(BigInteger, default=0)
    lifetime_spend: Mapped[int] = mapped_column(BigInteger, default=0)

    # Soft limits so a runaway bug doesn't empty a wallet
    daily_limit: Mapped[int] = mapped_column(BigInteger, default=0)  # 0 = unlimited
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ledger_entries: Mapped[list["TokenLedger"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class TokenLedger(Base, TimestampMixin):
    """Immutable transaction log — every top-up + spend + refund."""

    __tablename__ = "ai_token_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("ai_token_wallets.id", ondelete="CASCADE"),
        index=True,
    )

    op: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # topup | spend | refund | bonus | admin_adjust

    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # positive for topup/bonus, negative for spend/refund-out

    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # What caused this entry
    reference_type: Mapped[str] = mapped_column(String(32), default="")
    # "stripe_payment" | "ai_usage" | "promo" | "support_ticket"
    reference_id: Mapped[str] = mapped_column(String(128), default="")

    note: Mapped[str] = mapped_column(String(500), default="")

    wallet: Mapped[TokenWallet] = relationship(back_populates="ledger_entries")


class AiProvider(Base, TimestampMixin):
    """Registry of AI providers — internal routing table.

    These are NOT sold. Customers only see 'Pi AI Cloud' and pay in tokens.
    This table tells the router which backend to call and health status.
    """

    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # "gemini-free" | "cohere-free" | "groq-free" | "anthropic-paid" | ...

    display_name: Mapped[str] = mapped_column(String(128))
    adapter: Mapped[str] = mapped_column(String(32))
    # Which Python adapter class to use: "openai_compat" | "anthropic" | "gemini"

    base_url: Mapped[str] = mapped_column(String(500))
    model_id: Mapped[str] = mapped_column(String(128))
    # Real upstream model: "gemini-2.0-flash-exp", "llama-3.3-70b-versatile"

    # NOTE: API keys live in ai_provider_keys (pool). This table is metadata only.

    # Cost tracking for margin analysis
    input_cost_per_mtok_cents: Mapped[int] = mapped_column(Integer, default=0)
    output_cost_per_mtok_cents: Mapped[int] = mapped_column(Integer, default=0)
    # "mtok" = per 1M tokens. Free tier = 0.

    # How many Pi tokens to charge customer per model-token
    # (allows premium models to cost more Pi tokens per output)
    pi_tokens_per_input: Mapped[float] = mapped_column(Float, default=1.0)
    pi_tokens_per_output: Mapped[float] = mapped_column(Float, default=1.0)

    # Routing
    tier: Mapped[str] = mapped_column(String(16), default="free", index=True)
    # "free" routes most traffic here first; "paid" used as fallback for quality
    priority: Mapped[int] = mapped_column(Integer, default=100)
    # Lower = tried first

    # Quota limits (per hour/day across all customers combined)
    max_rpm: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    max_tpd: Mapped[int] = mapped_column(Integer, default=0)  # tokens per day

    # Health
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    health_status: Mapped[str] = mapped_column(String(16), default="healthy")
    # "healthy" | "degraded" | "down"
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class AiUsage(Base, TimestampMixin):
    """Per-request AI call log — for analytics + debugging + billing proof."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("ai_token_wallets.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    provider_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_provider_keys.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Where request came from (which Pi plugin)
    source_plugin: Mapped[str] = mapped_column(String(32), default="", index=True)
    # "pi-seo" | "pi-chatbot" | "pi-leads" | "direct_api"
    source_endpoint: Mapped[str] = mapped_column(String(64), default="")
    # "seo_bot.generate" | "chatbot.reply" | "leads.enrich"

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    pi_tokens_charged: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking (for Pi's internal margin view — never sent to customer)
    upstream_cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="success")
    error_code: Mapped[str] = mapped_column(String(64), default="")


class AiProviderKey(Base, TimestampMixin):
    """Pool of upstream API keys. Admin manually allocates keys to licenses.

    Lifecycle:
      - status='available' → unassigned, can be allocated
      - status='allocated' → assigned to a specific license
      - status='exhausted' → monthly quota hit; reset on period rollover
      - status='banned'    → upstream killed it; admin decides if reusable
    """

    __tablename__ = "ai_provider_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="CASCADE"), index=True
    )

    key_value: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str] = mapped_column(String(128), default="")
    # "groq-acct-17-sim-0909xxx" — admin-readable identifier

    status: Mapped[str] = mapped_column(String(16), default="available", index=True)

    allocated_to_license_id: Mapped[int | None] = mapped_column(
        ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    health_status: Mapped[str] = mapped_column(String(16), default="healthy")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    monthly_used_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    monthly_quota_tokens: Mapped[int] = mapped_column(BigInteger, default=0)  # 0 = unlimited
    period_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )

    notes: Mapped[str] = mapped_column(Text, default="")


class AiPackage(Base, TimestampMixin):
    """Subscription tier definition — customer-facing."""

    __tablename__ = "ai_packages"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")

    price_cents_monthly: Mapped[int] = mapped_column(Integer, default=0)
    price_cents_yearly: Mapped[int] = mapped_column(Integer, default=0)

    token_quota_monthly: Mapped[int] = mapped_column(BigInteger, default=0)  # 0 = unlimited

    allowed_qualities: Mapped[list] = mapped_column(JSON, nullable=False)
    # ['fast'] | ['fast','balanced'] | ['fast','balanced','best']

    features: Mapped[list] = mapped_column(JSON, default=list)
    # marketing bullets shown on pricing page

    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LicensePackage(Base, TimestampMixin):
    """Per-license subscription state + period-scoped usage counters."""

    __tablename__ = "license_packages"

    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), primary_key=True
    )
    package_slug: Mapped[str] = mapped_column(
        ForeignKey("ai_packages.slug"), index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(String(16), default="active")  # active|past_due|cancelled
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_subscription_id: Mapped[str] = mapped_column(String(128), default="")

    current_period_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    current_period_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
    current_period_requests: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
