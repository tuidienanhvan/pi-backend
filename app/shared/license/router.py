"""License endpoints — verify / activate / deactivate / stats."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentLicense, DbSession, LicenseForActivate
from app.pi_ai_cloud.models import AiPackage, LicensePackage
from app.shared.license.schemas import (
    LicenseActivateRequest,
    LicenseActivateResponse,
    LicenseStatsResponse,
    LicenseVerifyRequest,
    LicenseVerifyResponse,
)
from app.shared.license.service import LicenseService

router = APIRouter()


@router.post("/verify", response_model=LicenseVerifyResponse)
async def verify(
    req: LicenseVerifyRequest,
    lic: LicenseForActivate,
    db: DbSession,
) -> LicenseVerifyResponse:
    """Plugin calls this every 12-24h to confirm license still valid."""
    svc = LicenseService(db)

    # Touch the site's last_seen_at (silent reactivation)
    try:
        await svc.activate_site(
            lic,
            site_url=req.site_url,
            plugin_version=req.plugin_version,
            wp_version=req.wp_version,
            php_version=req.php_version,
        )
    except ValueError:
        # Max sites reached — still report license as valid,
        # but the site won't be listed as activated
        pass

    features = _features_for_tier(lic.tier)

    return LicenseVerifyResponse(
        success=True,
        tier=lic.tier,  # type: ignore[arg-type]
        status=lic.status,  # type: ignore[arg-type]
        expires_at=lic.expires_at,
        features=features,
    )


@router.post("/activate", response_model=LicenseActivateResponse)
async def activate(
    req: LicenseActivateRequest,
    lic: LicenseForActivate,
    db: DbSession,
) -> LicenseActivateResponse:
    """Called when user first installs + enters license key."""
    svc = LicenseService(db)
    try:
        site, created = await svc.activate_site(
            lic,
            site_url=req.site_url,
            plugin_version=req.plugin_version,
            wp_version=req.wp_version,
            php_version=req.php_version,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        ) from e

    count = await svc.activated_sites_count(lic)
    return LicenseActivateResponse(
        success=True,
        site_id=site.id,
        activated_sites=count,
        max_sites=lic.max_sites,
        message="Activated" if created else "Reactivated",
    )


@router.post("/deactivate")
async def deactivate(
    req: LicenseActivateRequest,
    lic: LicenseForActivate,
    db: DbSession,
) -> dict[str, bool]:
    svc = LicenseService(db)
    ok = await svc.deactivate_site(lic, req.site_url)
    return {"success": ok}


@router.get("/stats", response_model=LicenseStatsResponse)
async def stats(lic: LicenseForActivate, db: DbSession) -> LicenseStatsResponse:
    svc = LicenseService(db)
    count = await svc.activated_sites_count(lic)
    usage = await svc.usage_this_month(lic)
    quota = settings.monthly_quota_for.get(lic.tier, settings.rate_limit_free_per_month)

    # Pi AI Cloud package (optional, separate from license tier)
    pkg_row = await db.execute(
        select(LicensePackage, AiPackage)
        .join(AiPackage, LicensePackage.package_slug == AiPackage.slug)
        .where(LicensePackage.license_id == lic.id)
    )
    pkg_data = pkg_row.first()
    package_slug = None
    package_name = None
    package_status = None
    quota_limit = 0
    quota_used = 0
    if pkg_data:
        lp, ap = pkg_data
        package_slug = lp.package_slug
        package_name = ap.display_name
        package_status = lp.status
        quota_limit = int(ap.token_quota_monthly or 0)
        quota_used = int(lp.current_period_tokens_used or 0)

    return LicenseStatsResponse(
        key_prefix=lic.key[:12] + "...",
        tier=lic.tier,
        status=lic.status,
        email=lic.email,  # type: ignore[arg-type]
        max_sites=lic.max_sites,
        activated_sites=count,
        usage_this_month=usage,
        quota_this_month=quota,
        expires_at=lic.expires_at,
        package_slug=package_slug,
        package_tier=package_slug,  # convenience alias (same value)
        package_name=package_name,
        package_status=package_status,
        quota_limit=quota_limit,
        quota_used=quota_used,
    )


def _features_for_tier(tier: str) -> list[str]:
    """Advertise feature flags for the client plugin to gate UI."""
    base = ["meta_tags", "sitemap", "schema_basic", "audit_basic"]
    pro = base + [
        "seo_bot_ai",
        "schema_pro_templates",
        "audit_advanced",
        "schema_importer",
        "content_analysis",
        "gsc_extended",
        "mega_importer",
    ]
    agency = pro + [
        "bulk_ai",
        "api_access",
        "white_label",
        "multisite_unlimited",
    ]
    return {"free": base, "pro": pro, "agency": agency}.get(tier, base)
