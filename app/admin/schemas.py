"""Admin dashboard DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ─── Overview ──────────────────────────────────────────

class AdminOverviewResponse(BaseModel):
    revenue_30d: float
    upstream_cost_30d: float
    margin_pct: float
    active_licenses: int
    tokens_spent_30d: int
    total_providers: int
    healthy_providers: int
    down_providers: int
    top_plugins: list[dict]


# ─── Licenses ──────────────────────────────────────────

class AdminLicenseItem(BaseModel):
    id: int
    key: str
    email: str
    name: str = ""
    plugin: str
    tier: str
    status: str
    max_sites: int
    activated_sites: int
    expires_at: Optional[datetime] = None
    created_at: datetime
    # Cloud package state
    package_slug: Optional[str] = None
    package_name: Optional[str] = None
    quota_used: int = 0
    quota_limit: int = 0
    quota_pct: float = 0.0
    allocated_keys_count: int = 0
    last_active_at: Optional[datetime] = None


class AdminLicensesResponse(BaseModel):
    items: list[AdminLicenseItem]
    total: int
    limit: int = 50
    offset: int = 0
    facets: dict = {}


class AdminLicenseCreate(BaseModel):
    plugin: str
    email: str
    name: str = ""
    tier: str = "pro"
    max_sites: int = 1
    expires_days: int = 365
    notes: str = ""


class AdminLicensePatch(BaseModel):
    tier: Optional[str] = None
    max_sites: Optional[int] = None
    expires_at: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AdminTokenAdjust(BaseModel):
    delta: int
    note: str = ""


# ─── Users ─────────────────────────────────────────────

class AdminUserItem(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool
    is_verified: bool
    license_count: int
    token_balance: int
    total_spent_cents: int
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUsersResponse(BaseModel):
    items: list[AdminUserItem]
    total: int


# ─── Providers ─────────────────────────────────────────

class AdminProviderItem(BaseModel):
    id: int
    slug: str
    display_name: str
    adapter: str
    base_url: str
    model_id: str
    tier: str
    priority: int
    is_enabled: bool
    health_status: str
    input_cost_per_mtok_cents: int
    output_cost_per_mtok_cents: int
    pi_tokens_per_input: float
    pi_tokens_per_output: float
    consecutive_failures: int
    last_error: str = ""
    last_success_at: Optional[datetime] = None
    # Key pool stats (keys live in ai_provider_keys, not here)
    keys_total: int = 0
    keys_available: int = 0
    keys_allocated: int = 0
    has_api_key: bool = False  # deprecated alias: true if keys_total > 0


class AdminProvidersResponse(BaseModel):
    items: list[AdminProviderItem]


class AdminProviderPatch(BaseModel):
    """Partial update — all fields optional. NOTE: API keys live in /admin/keys now."""

    display_name: Optional[str] = None
    adapter: Optional[str] = None
    base_url: Optional[str] = None
    model_id: Optional[str] = None
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None
    tier: Optional[str] = None
    input_cost_per_mtok_cents: Optional[int] = None
    output_cost_per_mtok_cents: Optional[int] = None
    pi_tokens_per_input: Optional[float] = None
    pi_tokens_per_output: Optional[float] = None
    # Accepted but IGNORED (compat for old UI): deposit key into pool via /admin/keys
    api_key: Optional[str] = None


class AdminProviderCreate(BaseModel):
    slug: str
    display_name: str
    adapter: str = "openai_compat"
    base_url: str
    model_id: str
    tier: str = "free"
    priority: int = 100
    input_cost_per_mtok_cents: int = 0
    output_cost_per_mtok_cents: int = 0
    pi_tokens_per_input: float = 1.0
    pi_tokens_per_output: float = 1.0
    is_enabled: bool = True
    # If provided, auto-seeds 1 key into the pool for convenience
    api_key: str = ""


class AdminProviderTestResult(BaseModel):
    ok: bool
    latency_ms: int
    sample: str = ""
    error: str = ""


# ─── Settings (global platform config) ────────────────

class BrandingSettings(BaseModel):
    site_name: str = "Pi Ecosystem"
    logo_url: str = "/logo.svg"
    primary_color: str = "#007d3d"
    support_email: str = ""


class TokenPack(BaseModel):
    slug: str
    tokens: int
    price_cents: int
    discount_pct: int = 0
    label: str = ""


class FeatureFlags(BaseModel):
    signup_enabled: bool = True
    billing_enabled: bool = True
    marketplace_enabled: bool = True
    maintenance_mode: bool = False  # blocks /v1/ai/complete when true


class AdminSettingsResponse(BaseModel):
    branding: BrandingSettings
    token_packs: list[TokenPack]
    feature_flags: FeatureFlags


class AdminSettingsUpdate(BaseModel):
    branding: Optional[BrandingSettings] = None
    token_packs: Optional[list[TokenPack]] = None
    feature_flags: Optional[FeatureFlags] = None


# ─── Usage ─────────────────────────────────────────────

class AdminUsageRow(BaseModel):
    plugin: str
    calls: int
    tokens: int
    revenue_usd: float
    upstream_usd: float
    margin_pct: float


class AdminUsageResponse(BaseModel):
    total_calls: int
    tokens_spent: int
    upstream_cost_cents: int
    avg_latency_ms: int
    by_plugin: list[AdminUsageRow]
    daily: list[dict] = []     # [{date, success, fail, tokens}, …]
    errors: list[dict] = []    # [{code, count, sample}, …]


# ─── Revenue ───────────────────────────────────────────

class AdminRevenueRow(BaseModel):
    sku: str
    name: str
    type: str
    count: int
    revenue_cents: int


class AdminRevenueResponse(BaseModel):
    revenue_cents: int
    cost_cents: int
    margin_pct: float
    by_product: list[AdminRevenueRow]


# ─── Releases ──────────────────────────────────────────

class AdminReleaseItem(BaseModel):
    id: int
    plugin_slug: str
    version: str
    tier_required: str
    zip_size_bytes: int
    zip_sha256: str
    is_stable: bool
    is_yanked: bool
    created_at: datetime


class AdminReleasesResponse(BaseModel):
    items: list[AdminReleaseItem]
