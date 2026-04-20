"""Pi AI Cloud — DTOs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────
# Completion (primary endpoint)
# ─────────────────────────────────────────────────────────────


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompleteRequest(BaseModel):
    messages: list[Message] = Field(..., min_length=1, max_length=50)
    max_tokens: int = Field(1024, ge=1, le=8192)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    # Quality tier — lets Pi choose cheaper provider for draft work
    quality: Literal["fast", "balanced", "best"] = "balanced"
    # Optional: which Pi plugin made the call (billing attribution)
    source_plugin: str = ""
    source_endpoint: str = ""


class CompleteResponse(BaseModel):
    success: bool
    text: str
    pi_tokens_charged: int
    # Quota snapshot (replaces wallet_balance — customers now have period quotas)
    tokens_used_period: int
    tokens_limit_period: int  # 0 = unlimited
    input_tokens: int
    output_tokens: int
    # NOTE: provider_slug is intentionally NOT exposed to customers.
    # Upstream routing is Pi's internal concern — customers just send requests.


# ─────────────────────────────────────────────────────────────
# Wallet + tokens
# ─────────────────────────────────────────────────────────────


class WalletResponse(BaseModel):
    balance: int
    lifetime_topup: int
    lifetime_spend: int
    daily_limit: int
    last_activity_at: datetime | None = None


class LedgerEntry(BaseModel):
    id: int
    op: str
    delta: int
    balance_after: int
    reference_type: str
    note: str
    created_at: datetime


class LedgerResponse(BaseModel):
    entries: list[LedgerEntry]
    has_more: bool


class TopupCheckoutRequest(BaseModel):
    """Customer clicks 'Buy 100k tokens' → Stripe Checkout URL."""

    pack: Literal["10k", "100k", "500k", "1m", "5m"] = "100k"
    success_url: str
    cancel_url: str


class TopupCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


# ─────────────────────────────────────────────────────────────
# Admin / debugging
# ─────────────────────────────────────────────────────────────


class ProviderInfo(BaseModel):
    slug: str
    display_name: str
    tier: str
    health_status: str
    model_id: str


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]
    note: str = "Providers are routed automatically — customers cannot select."
