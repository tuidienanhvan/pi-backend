"""Admin schemas — Pi AI Cloud: keys pool + packages + license allocation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ─── Provider Keys (pool) ────────────────────────────────

class AdminKeyItem(BaseModel):
    id: int
    provider_id: int
    provider_slug: str
    provider_display_name: str
    label: str
    key_masked: str  # never raw key
    status: str
    allocated_to_license_id: Optional[int] = None
    allocated_to_email: Optional[str] = None
    allocated_at: Optional[datetime] = None
    health_status: str
    consecutive_failures: int
    last_error: str = ""
    last_success_at: Optional[datetime] = None
    monthly_used_tokens: int
    monthly_quota_tokens: int
    notes: str = ""


class AdminKeysResponse(BaseModel):
    items: list[AdminKeyItem]
    total: int


class AdminKeyCreate(BaseModel):
    provider_id: Optional[int] = None
    provider_slug: Optional[str] = None
    key_value: str
    label: str = ""
    monthly_quota_tokens: int = 0
    notes: str = ""


class AdminKeyPatch(BaseModel):
    key_value: Optional[str] = None  # rotate the key string
    label: Optional[str] = None
    status: Optional[str] = None  # available|allocated|exhausted|banned
    monthly_quota_tokens: Optional[int] = None
    notes: Optional[str] = None


class AdminKeyBulkRow(BaseModel):
    provider_slug: str
    key_value: str
    label: str = ""
    monthly_quota_tokens: int = 0


class AdminKeyBulkImport(BaseModel):
    rows: list[AdminKeyBulkRow]


class AdminKeyBulkResult(BaseModel):
    added: int
    skipped: int
    errors: list[str] = []


class AdminKeyAllocate(BaseModel):
    license_id: int
    provider_id: Optional[int] = None  # if set, auto-pick N available keys
    count: int = 1
    key_ids: Optional[list[int]] = None  # or specify exact keys


class AdminPoolSummaryRow(BaseModel):
    provider_id: int
    slug: str
    display_name: str
    available: int
    allocated: int
    exhausted: int
    banned: int
    total: int


class AdminPoolSummary(BaseModel):
    items: list[AdminPoolSummaryRow]


# ─── Packages ────────────────────────────────────────────

class AdminPackageItem(BaseModel):
    slug: str
    display_name: str
    description: str = ""
    price_cents_monthly: int
    price_cents_yearly: int
    token_quota_monthly: int
    allowed_qualities: list[str]
    features: list[str]
    sort_order: int
    is_active: bool


class AdminPackagesResponse(BaseModel):
    items: list[AdminPackageItem]


class AdminPackageCreate(BaseModel):
    slug: str
    display_name: str
    description: str = ""
    price_cents_monthly: int = 0
    price_cents_yearly: int = 0
    token_quota_monthly: int = 0
    allowed_qualities: list[str] = ["fast"]
    features: list[str] = []
    sort_order: int = 100
    is_active: bool = True


class AdminPackagePatch(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    price_cents_monthly: Optional[int] = None
    price_cents_yearly: Optional[int] = None
    token_quota_monthly: Optional[int] = None
    allowed_qualities: Optional[list[str]] = None
    features: Optional[list[str]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ─── License ↔ Package ──────────────────────────────────

class AdminLicensePackageItem(BaseModel):
    license_id: int
    package_slug: str
    package_name: str
    status: str
    activated_at: datetime
    renews_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    current_period_started_at: datetime
    current_period_tokens_used: int
    token_quota_monthly: int
    allocated_keys_count: int


class AdminAssignPackage(BaseModel):
    package_slug: str
    expires_at: Optional[datetime] = None
