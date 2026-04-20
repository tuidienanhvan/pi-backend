"""Telemetry — anonymous plugin heartbeat + site counts."""

from fastapi import APIRouter

from app.core.deps import CurrentLicense, DbSession
from app.shared.telemetry.schemas import TelemetryPingRequest, TelemetryPingResponse
from app.shared.license.service import LicenseService

router = APIRouter()


@router.post("/ping", response_model=TelemetryPingResponse)
async def ping(
    req: TelemetryPingRequest,
    lic: CurrentLicense,
    db: DbSession,
) -> TelemetryPingResponse:
    """Plugin calls this daily (or on activate) to report site metadata."""
    svc = LicenseService(db)
    try:
        await svc.activate_site(
            lic,
            site_url=req.site_url,
            plugin_version=req.plugin_version,
            wp_version=req.wp_version,
            php_version=req.php_version,
        )
    except ValueError:
        pass  # over limit — silent, license.verify would have failed first

    # Optional: return an admin notice (e.g., "Pi SEO 1.4.0 available!")
    notice = None
    if req.plugin_slug == "pi-seo":
        # Placeholder logic — look up latest PluginRelease and compare
        notice = None

    return TelemetryPingResponse(
        success=True,
        next_ping_hours=24,
        admin_notice=notice,
    )
