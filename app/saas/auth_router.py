"""Root /auth endpoints consumed by the Pi API WordPress plugin."""

from datetime import datetime, timezone
import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DbSession
from app.saas.jwt import create_tenant_token
from app.saas.models import AdminAuditLog, Tenant, Token
from app.saas.schemas import (
    ActivateRequest,
    ActivateResponse,
    DeactivateResponse,
    HeartbeatResponse,
    JwtResponse,
    LicensePayload,
)
from app.saas.tiers import features_for_tier, monthly_quota_for_tier, normalize_tier

router = APIRouter()


def _validate_license_key(key: str) -> None:
    if not re.match(settings.tenant_license_key_pattern, key):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid license key format")


def _tenant_payload(tenant: Tenant) -> dict:
    return {
        "tenant_id": tenant.id,
        "tier": tenant.tier,
        "features": list(tenant.features or []),
        "status": tenant.status,
    }


def _tier_from_license_key(key: str) -> str:
    if "MAX" in key or "AGENCY" in key or "AGNCY" in key:
        return "max"
    if "PRO" in key:
        return "pro"
    return normalize_tier(settings.license_default_tier)


async def _audit(db: DbSession, action: str, tenant: Tenant | None, metadata: dict | None = None) -> None:
    db.add(
        AdminAuditLog(
            actor="pi-api",
            action=action,
            tenant_id=tenant.id if tenant else None,
            metadata_=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
    )


async def _find_tenant(db: DbSession, payload: LicensePayload) -> Tenant:
    _validate_license_key(payload.license_key)
    q = select(Tenant).where(
        Tenant.license_key == payload.license_key,
        Tenant.domain == payload.domain,
    )
    tenant = (await db.execute(q)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not activated")
    return tenant


@router.post("/activate", response_model=ActivateResponse)
async def activate(payload: ActivateRequest, db: DbSession) -> ActivateResponse:
    _validate_license_key(payload.license_key)
    q = select(Tenant).where(Tenant.license_key == payload.license_key)
    existing_by_key = (await db.execute(q)).scalar_one_or_none()
    if existing_by_key is not None and existing_by_key.domain != payload.domain:
        raise HTTPException(status.HTTP_409_CONFLICT, "License is already bound to another domain")

    q = select(Tenant).where(Tenant.domain == payload.domain)
    tenant = (await db.execute(q)).scalar_one_or_none()
    if tenant is None:
        tier = _tier_from_license_key(payload.license_key)
        tenant = Tenant(
            license_key=payload.license_key,
            domain=payload.domain,
            site_url=payload.site_url,
            tier=tier,
            status="active",
            features=features_for_tier(tier),
            wp_version=payload.wp_version,
            plugin_version=payload.plugin_ver,
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(tenant)
        await db.flush()
        db.add(
            Token(
                tenant_id=tenant.id,
                balance=0,
                monthly_quota=monthly_quota_for_tier(tier),
                used_this_month=0,
            )
        )
        await _audit(db, "tenant.activate", tenant, {"domain": tenant.domain, "tier": tenant.tier})
    else:
        if tenant.license_key != payload.license_key:
            raise HTTPException(status.HTTP_409_CONFLICT, "Domain is already bound to another license")
        tenant.status = "active"
        tenant.site_url = payload.site_url or tenant.site_url
        tenant.wp_version = payload.wp_version or tenant.wp_version
        tenant.plugin_version = payload.plugin_ver or tenant.plugin_version
        tenant.last_seen_at = datetime.now(timezone.utc)
        await _audit(db, "tenant.reactivate", tenant, {"domain": tenant.domain})

    return ActivateResponse(**_tenant_payload(tenant))


@router.post("/issue-jwt", response_model=JwtResponse)
async def issue_jwt(payload: LicensePayload, db: DbSession) -> JwtResponse:
    tenant = await _find_tenant(db, payload)
    if tenant.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant inactive")
    token, expires_in = create_tenant_token(
        tenant_id=tenant.id,
        domain=tenant.domain,
        tier=tenant.tier,
        features=list(tenant.features or []),
    )
    await _audit(db, "tenant.issue_jwt", tenant)
    return JwtResponse(jwt=token, expires_in=expires_in)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(payload: LicensePayload, db: DbSession) -> HeartbeatResponse:
    tenant = await _find_tenant(db, payload)
    if tenant.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant inactive")
    tenant.last_seen_at = datetime.now(timezone.utc)
    await _audit(db, "tenant.heartbeat", tenant)
    return HeartbeatResponse(**_tenant_payload(tenant), last_seen_at=tenant.last_seen_at)


@router.post("/deactivate", response_model=DeactivateResponse)
async def deactivate(payload: LicensePayload, db: DbSession) -> DeactivateResponse:
    tenant = await _find_tenant(db, payload)
    tenant.status = "inactive"
    await _audit(db, "tenant.deactivate", tenant, {"domain": tenant.domain})
    return DeactivateResponse()
