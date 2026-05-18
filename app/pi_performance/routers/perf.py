"""Pi Performance — CDN purge + Critical CSS + image compression."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import RateLimitedLicense

router = APIRouter()


class CdnPurgeRequest(BaseModel):
    urls: list[str]


class CriticalCssRequest(BaseModel):
    url: str


@router.post("/cdn/purge")
async def cdn_purge(req: CdnPurgeRequest, lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    """Purge CDN cache for given URLs. PHASE 4 — not yet wired.

    Requires Cloudflare API token (CF_API_TOKEN env) + httpx proxy call.
    Returns 501 so plugins detect unwired state instead of fake success.
    """
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail="CDN purge not implemented — Phase 4 (requires CF_API_TOKEN + Cloudflare API integration)",
    )


@router.post("/critical-css")
async def critical_css(req: CriticalCssRequest, lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    """Generate above-the-fold CSS for URL. PHASE 4 — not yet wired.

    Requires headless browser (Puppeteer via Modal/Cloud Run worker) and
    token-charging logic. Returns 501 instead of fake CSS so plugins
    don't accidentally inject placeholder body{margin:0} into production.
    """
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail="Critical CSS not implemented — Phase 4 (requires headless browser worker)",
    )


@router.get("/status")
async def status(lic: RateLimitedLicense) -> dict:
    return {"plugin": "pi-performance", "tier": lic.tier, "endpoints": ["cdn/purge", "critical-css"]}
