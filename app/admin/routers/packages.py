"""/v1/admin/packages/* — subscription package CRUD.

Packages define customer-facing tiers: price, token quota, allowed quality
levels. Admin separately allocates keys to each license (keys are NOT
bundled with the package).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.admin.schemas_cloud import (
    AdminAssignPackage,
    AdminLicensePackageItem,
    AdminPackageCreate,
    AdminPackageItem,
    AdminPackagePatch,
    AdminPackagesResponse,
)
from app.core.deps import DbSession
from app.pi_ai_cloud.models import AiPackage, AiProviderKey, LicensePackage
from app.shared.auth.deps import CurrentAdmin
from app.shared.license.models import License
from sqlalchemy import func, select

router = APIRouter()


def _to_item(p: AiPackage) -> AdminPackageItem:
    return AdminPackageItem(
        slug=p.slug, display_name=p.display_name, description=p.description or "",
        price_cents_monthly=p.price_cents_monthly, price_cents_yearly=p.price_cents_yearly,
        token_quota_monthly=p.token_quota_monthly,
        allowed_qualities=list(p.allowed_qualities or []),
        features=list(p.features or []),
        sort_order=p.sort_order, is_active=p.is_active,
    )


@router.get("/packages", response_model=AdminPackagesResponse)
async def list_packages(admin: CurrentAdmin, db: DbSession) -> AdminPackagesResponse:  # noqa: ARG001
    q = select(AiPackage).order_by(AiPackage.sort_order.asc(), AiPackage.slug.asc())
    items = list((await db.execute(q)).scalars().all())
    return AdminPackagesResponse(items=[_to_item(p) for p in items])


@router.post("/packages", response_model=AdminPackageItem, status_code=201)
async def create_package(
    payload: AdminPackageCreate, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminPackageItem:
    existing = await db.get(AiPackage, payload.slug)
    if existing is not None:
        raise HTTPException(409, f"Package slug '{payload.slug}' already exists")
    p = AiPackage(**payload.model_dump())
    db.add(p)
    await db.flush()
    return _to_item(p)


@router.patch("/packages/{slug}", response_model=AdminPackageItem)
async def patch_package(
    slug: str, payload: AdminPackagePatch, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminPackageItem:
    p = await db.get(AiPackage, slug)
    if p is None:
        raise HTTPException(404, "Package not found")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, f, v)
    await db.flush()
    return _to_item(p)


@router.delete("/packages/{slug}", status_code=204)
async def delete_package(
    slug: str, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> None:
    p = await db.get(AiPackage, slug)
    if p is None:
        raise HTTPException(404, "Package not found")
    # Prevent deleting a package with active subscribers
    in_use = (await db.execute(
        select(func.count(LicensePackage.license_id)).where(LicensePackage.package_slug == slug)
    )).scalar_one()
    if int(in_use) > 0:
        raise HTTPException(409, f"Package '{slug}' still assigned to {in_use} licenses")
    await db.delete(p)
    await db.flush()


# ─── License ↔ Package assignment ────────────────────────


@router.get("/licenses/{license_id}/package", response_model=AdminLicensePackageItem | None)
async def get_license_package(
    license_id: int, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminLicensePackageItem | None:
    row = (await db.execute(
        select(LicensePackage, AiPackage)
        .join(AiPackage, AiPackage.slug == LicensePackage.package_slug)
        .where(LicensePackage.license_id == license_id)
    )).first()
    if row is None:
        return None
    lp, ap = row
    keys_count = int((await db.execute(
        select(func.count(AiProviderKey.id)).where(AiProviderKey.allocated_to_license_id == license_id)
    )).scalar_one())
    return AdminLicensePackageItem(
        license_id=lp.license_id, package_slug=ap.slug, package_name=ap.display_name,
        status=lp.status, activated_at=lp.activated_at,
        renews_at=lp.renews_at, expires_at=lp.expires_at,
        current_period_started_at=lp.current_period_started_at,
        current_period_tokens_used=lp.current_period_tokens_used,
        token_quota_monthly=ap.token_quota_monthly,
        allocated_keys_count=keys_count,
    )


@router.post("/licenses/{license_id}/package", response_model=AdminLicensePackageItem)
async def assign_package(
    license_id: int, payload: AdminAssignPackage,
    admin: CurrentAdmin, db: DbSession,  # noqa: ARG001
) -> AdminLicensePackageItem:
    lic = await db.get(License, license_id)
    if lic is None:
        raise HTTPException(404, "License not found")
    pkg = await db.get(AiPackage, payload.package_slug)
    if pkg is None:
        raise HTTPException(404, f"Package '{payload.package_slug}' not found")

    now = datetime.now(timezone.utc)
    lp = await db.get(LicensePackage, license_id)
    if lp is None:
        lp = LicensePackage(
            license_id=license_id,
            package_slug=payload.package_slug,
            status="active",
            activated_at=now,
            expires_at=payload.expires_at,
            current_period_started_at=now,
            current_period_tokens_used=0,
        )
        db.add(lp)
    else:
        lp.package_slug = payload.package_slug
        lp.status = "active"
        lp.expires_at = payload.expires_at
        # Reset period when switching package
        lp.current_period_started_at = now
        lp.current_period_tokens_used = 0
        lp.current_period_requests = 0
    await db.flush()

    return await get_license_package(license_id, admin, db)  # type: ignore


@router.post("/licenses/{license_id}/package/reset-period", response_model=AdminLicensePackageItem)
async def reset_period(
    license_id: int, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminLicensePackageItem:
    lp = await db.get(LicensePackage, license_id)
    if lp is None:
        raise HTTPException(404, "License has no package")
    lp.current_period_started_at = datetime.now(timezone.utc)
    lp.current_period_tokens_used = 0
    lp.current_period_requests = 0
    await db.flush()
    return await get_license_package(license_id, admin, db)  # type: ignore
