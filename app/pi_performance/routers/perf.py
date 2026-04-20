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
    """Purge CDN cache for given URLs. Needs Cloudflare API token (stored server-side)."""
    # Placeholder — real impl needs httpx call to Cloudflare API with CF_API_TOKEN env
    return {
        "success": True,
        "purged": len(req.urls),
        "note": "Cloudflare proxy — requires CF_API_TOKEN env on backend (Phase 4)",
    }


@router.post("/critical-css")
async def critical_css(req: CriticalCssRequest, lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    """Generate above-the-fold CSS for URL. Normally uses headless browser."""
    # Placeholder — real impl runs Puppeteer via Modal / Cloud Run; consumes tokens.
    return {
        "success": True,
        "css": "/* Pi Critical CSS placeholder — Phase 4 will run Puppeteer */\nbody{margin:0;}",
        "url": req.url,
    }


@router.get("/status")
async def status(lic: RateLimitedLicense) -> dict:
    return {"plugin": "pi-performance", "tier": lic.tier, "endpoints": ["cdn/purge", "critical-css"]}
