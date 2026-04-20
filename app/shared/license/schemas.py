"""License request/response DTOs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LicenseVerifyRequest(BaseModel):
    """Plugin sends `Authorization: Bearer pi_xxxxxx` + this body."""

    site_url: str = Field(..., description="https://example.com")
    plugin_version: str = ""
    wp_version: str = ""
    php_version: str = ""


class LicenseVerifyResponse(BaseModel):
    success: bool
    tier: Literal["free", "pro", "agency"]
    status: Literal["active", "expired", "revoked", "suspended"]
    expires_at: datetime | None = None
    features: list[str] = Field(default_factory=list)
    message: str = ""


class LicenseActivateRequest(BaseModel):
    site_url: str
    plugin_version: str = ""
    wp_version: str = ""
    php_version: str = ""


class LicenseActivateResponse(BaseModel):
    success: bool
    site_id: int | None = None
    activated_sites: int
    max_sites: int
    message: str = ""


class LicenseStatsResponse(BaseModel):
    key_prefix: str  # First 12 chars of key for display
    tier: str
    status: str
    email: EmailStr
    max_sites: int
    activated_sites: int
    usage_this_month: int
    quota_this_month: int
    expires_at: datetime | None = None

    # ── Pi AI Cloud package (monthly token subscription, independent of license tier) ──
    package_slug: str | None = None   # 'starter' | 'pro' | 'agency' | None
    package_tier: str | None = None   # same value as slug, convenience alias
    package_name: str | None = None   # display name
    package_status: str | None = None # 'active' | 'past_due' | 'cancelled'
    quota_limit: int = 0              # monthly token quota from package (0 = none/unlimited)
    quota_used: int = 0               # tokens used in current period
