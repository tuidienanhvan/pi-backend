"""/v1/admin/licenses/* — create, list, patch, revoke, adjust tokens."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.admin.audit import AuditLogger
from app.admin.schemas import (
    AdminLicenseCreate,
    AdminLicenseItem,
    AdminLicensePatch,
    AdminLicensesResponse,
    AdminTokenAdjust,
)
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.pi_ai_cloud.services.wallet import WalletService
from app.shared.auth.deps import CurrentAdmin


def _req_ctx(req: Request) -> dict:
    return {
        "ip_address": req.client.host if req.client else "",
        "user_agent": req.headers.get("user-agent", "")[:500],
        "request_id": req.headers.get("x-request-id", ""),
    }

router = APIRouter()


def _to_item(lic, sites_count: int) -> AdminLicenseItem:
    return AdminLicenseItem(
        id=lic.id, key=lic.key, email=lic.email, name=lic.customer_name or "",
        plugin=lic.plugin,
        tier=lic.tier, status=lic.status, max_sites=lic.max_sites,
        activated_sites=sites_count, expires_at=lic.expires_at,
        created_at=lic.created_at,
    )


@router.get("/licenses", response_model=AdminLicensesResponse)
async def list_licenses(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    q: str = Query("", description="Free-text search in email/key/name"),
    tier: str = Query("", description="free|pro"),
    status: str = Query("", description="active|revoked|expired"),
    plugin: str = Query(""),
    package: str = Query("", description="Package slug"),
    expires_in: str = Query("", description="7d|30d|90d|expired"),
    sort: str = Query("-created_at"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminLicensesResponse:
    items, total, facets = await AdminService(db).list_licenses(
        q=q, tier=tier, status=status, plugin=plugin, package=package,
        expires_in=expires_in, sort=sort, limit=limit, offset=offset,
    )
    return AdminLicensesResponse(
        items=items, total=total, limit=limit, offset=offset, facets=facets,
    )


@router.post("/licenses", response_model=AdminLicenseItem)
async def create_license(
    payload: AdminLicenseCreate,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
) -> AdminLicenseItem:
    lic = await AdminService(db).create_license(payload)
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="create", resource_type="license",
        resource_id=lic.id, resource_label=f"{lic.email} / {lic.plugin}",
        after={"email": lic.email, "plugin": lic.plugin, "tier": lic.tier, "max_sites": lic.max_sites},
        message=f"Created license #{lic.id} for {lic.email}",
        **_req_ctx(request),
    )
    return _to_item(lic, sites_count=0)


@router.patch("/licenses/{license_id}", response_model=AdminLicenseItem)
async def patch_license(
    license_id: int,
    payload: AdminLicensePatch,
    admin: CurrentAdmin,
    db: DbSession,
) -> AdminLicenseItem:  # noqa: ARG001
    lic = await AdminService(db).patch_license(license_id, payload)
    if lic is None:
        raise HTTPException(404, "License not found")
    return _to_item(lic, sites_count=0)


@router.post("/licenses/{license_id}/revoke")
async def revoke_license(
    license_id: int, admin: CurrentAdmin, db: DbSession, request: Request,
) -> dict:
    ok = await AdminService(db).revoke_license(license_id)
    if not ok:
        raise HTTPException(404, "License not found")
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="revoke", resource_type="license", resource_id=license_id,
        message=f"Revoked license #{license_id}",
        severity="warning", **_req_ctx(request),
    )
    return {"success": True}


@router.post("/licenses/{license_id}/reactivate")
async def reactivate_license(
    license_id: int, admin: CurrentAdmin, db: DbSession, request: Request,
) -> dict:
    from app.shared.license.models import License
    lic = await db.get(License, license_id)
    if lic is None:
        raise HTTPException(404, "License not found")
    lic.status = "active"
    await db.flush()
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="reactivate", resource_type="license", resource_id=license_id,
        message=f"Reactivated license #{license_id}",
        **_req_ctx(request),
    )
    return {"success": True, "status": lic.status}


@router.delete("/licenses/{license_id}", status_code=204)
async def delete_license(
    license_id: int, admin: CurrentAdmin, db: DbSession, request: Request,
) -> None:
    """Hard delete a license. Also frees any allocated keys back to the pool."""
    from sqlalchemy import update
    from app.pi_ai_cloud.models import AiProviderKey, LicensePackage
    from app.shared.license.models import License

    lic = await db.get(License, license_id)
    if lic is None:
        raise HTTPException(404, "License not found")

    before = {
        "email": lic.email, "plugin": lic.plugin, "tier": lic.tier,
        "status": lic.status, "max_sites": lic.max_sites,
    }

    await db.execute(
        update(AiProviderKey)
        .where(AiProviderKey.allocated_to_license_id == license_id)
        .values(status="available", allocated_to_license_id=None, allocated_at=None)
    )
    lp = await db.get(LicensePackage, license_id)
    if lp is not None:
        await db.delete(lp)

    await db.delete(lic)
    await db.flush()

    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="delete", resource_type="license", resource_id=license_id,
        resource_label=before["email"], before=before,
        message=f"Deleted license #{license_id} ({before['email']}) — keys returned to pool",
        severity="critical", **_req_ctx(request),
    )


@router.post("/licenses/{license_id}/tokens")
async def adjust_tokens(
    license_id: int,
    payload: AdminTokenAdjust,
    admin: CurrentAdmin,
    db: DbSession,
) -> dict:  # noqa: ARG001
    """Manually add/subtract tokens (support refund, promo, etc.)."""
    lic = await db.get(
        (await __import__("app.shared.license.models", fromlist=["License"]).License),
        license_id,
    ) if False else None  # workaround if module import order flaky

    from app.shared.license.models import License
    lic = await db.get(License, license_id)
    if lic is None:
        raise HTTPException(404, "License not found")

    svc = WalletService(db)
    wallet = await svc.get_or_create(lic)

    if payload.delta > 0:
        entry = await svc.topup(
            wallet, payload.delta,
            op="admin_adjust",
            reference_type="admin",
            note=payload.note or f"Admin adjust by {admin.email}",
        )
    elif payload.delta < 0:
        from app.pi_ai_cloud.services.wallet import InsufficientTokens
        try:
            entry = await svc.spend(
                wallet, -payload.delta,
                reference_type="admin_debit",
                note=payload.note or f"Admin debit by {admin.email}",
            )
        except InsufficientTokens as e:
            raise HTTPException(409, f"Insufficient: balance={e.balance}") from e
    else:
        return {"success": True, "delta": 0, "balance_after": wallet.balance}

    return {
        "success": True,
        "delta": payload.delta,
        "balance_after": wallet.balance,
        "ledger_id": entry.id,
    }
