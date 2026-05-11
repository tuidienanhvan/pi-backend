"""Pydantic contracts for Pi API plugin activation and tenant admin."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _clean_domain(value: str) -> str:
    domain = value.strip().lower()
    domain = domain.removeprefix("http://").removeprefix("https://").split("/", 1)[0]
    if not domain:
        raise ValueError("domain is required")
    return domain


class LicensePayload(BaseModel):
    license_key: str = Field(min_length=8, max_length=96)
    domain: str = Field(min_length=1, max_length=255)

    @field_validator("license_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return _clean_domain(value)


class ActivateRequest(LicensePayload):
    site_url: str = ""
    wp_version: str = ""
    plugin_ver: str = ""


class ActivateResponse(BaseModel):
    success: bool = True
    tenant_id: int
    tier: str
    features: list[str]
    status: str


class JwtResponse(BaseModel):
    success: bool = True
    jwt: str
    expires_in: int


class HeartbeatResponse(ActivateResponse):
    last_seen_at: datetime


class DeactivateResponse(BaseModel):
    success: bool = True


class TenantItem(BaseModel):
    id: int
    domain: str
    site_url: str
    tier: str
    status: str
    features: list[str]
    last_seen_at: datetime | None = None


class TenantCreate(BaseModel):
    license_key: str = Field(min_length=8, max_length=96)
    domain: str = Field(min_length=1, max_length=255)
    site_url: str = ""
    tier: str = "free"
    status: str = "active"

    @field_validator("license_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return _clean_domain(value)


class TenantPatch(BaseModel):
    tier: str | None = None
    status: str | None = None
    features: list[str] | None = None


class TokenRechargeRequest(BaseModel):
    delta: int = Field(..., ge=1, le=1_000_000)
    reason: str = "admin_recharge"
    note: str = ""

