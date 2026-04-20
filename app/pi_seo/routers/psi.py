"""POST /v1/seo/psi/check — proxy to Google PageSpeed Insights.

Reads GOOGLE_PSI_API_KEY from settings. Results cached 1h in Redis.
Free tier: 25,000 queries/day without key, with key higher.
"""

import hashlib
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentLicense
from app.core.exceptions import PiException

router = APIRouter()

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PsiCheckRequest(BaseModel):
    url: str
    strategy: str = Field("mobile", pattern="^(mobile|desktop)$")
    categories: list[str] = Field(
        default_factory=lambda: ["performance", "accessibility", "best-practices", "seo"],
    )


class PsiScore(BaseModel):
    performance: float | None = None
    accessibility: float | None = None
    best_practices: float | None = None
    seo: float | None = None


class PsiCoreWebVitals(BaseModel):
    lcp_ms: int | None = None       # Largest Contentful Paint
    fid_ms: int | None = None       # First Input Delay
    cls: float | None = None        # Cumulative Layout Shift
    fcp_ms: int | None = None       # First Contentful Paint
    tbt_ms: int | None = None       # Total Blocking Time
    ttfb_ms: int | None = None      # Time to First Byte


class PsiCheckResponse(BaseModel):
    url: str
    strategy: str
    fetched_at: str
    scores: PsiScore
    core_web_vitals: PsiCoreWebVitals
    opportunities: list[dict] = []   # top 5 improvement suggestions
    cached: bool = False


def _score(lighthouse: dict, category: str) -> float | None:
    cat = lighthouse.get("categories", {}).get(category)
    if not cat or cat.get("score") is None:
        return None
    return round(cat["score"] * 100, 1)


def _audit_numeric(lighthouse: dict, audit_id: str) -> int | None:
    a = lighthouse.get("audits", {}).get(audit_id)
    if not a:
        return None
    v = a.get("numericValue")
    return int(v) if v is not None else None


def _audit_score_float(lighthouse: dict, audit_id: str) -> float | None:
    a = lighthouse.get("audits", {}).get(audit_id)
    if not a:
        return None
    v = a.get("numericValue")
    return round(v, 3) if v is not None else None


@router.post("/check", response_model=PsiCheckResponse)
async def psi_check(
    payload: PsiCheckRequest,
    lic: CurrentLicense,  # noqa: ARG001 — license only required for auth
) -> PsiCheckResponse:
    # Cache key
    cache_key_src = f"psi:{payload.strategy}:{payload.url}"
    cache_key = "psi:" + hashlib.sha256(cache_key_src.encode()).hexdigest()[:16]

    # Try Redis cache
    try:
        from app.core.redis_client import get_redis
        redis_client = await get_redis()
        cached_raw = await redis_client.get(cache_key)
        if cached_raw:
            import json
            obj = json.loads(cached_raw)
            obj["cached"] = True
            return PsiCheckResponse(**obj)
    except Exception:  # noqa: BLE001
        pass  # cache miss or redis unavailable — proceed to live fetch

    # Live fetch
    params = {"url": payload.url, "strategy": payload.strategy}
    for cat in payload.categories:
        params.setdefault("category", cat)  # httpx handles list via repeated param
    params["category"] = payload.categories

    psi_key = getattr(settings, "google_psi_api_key", None) or ""
    if psi_key:
        params["key"] = psi_key

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(PSI_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise PiException(
            status_code=502, code="psi_upstream_error",
            message=f"Google PSI returned {e.response.status_code}: {e.response.text[:300]}",
        ) from e
    except httpx.RequestError as e:
        raise PiException(
            status_code=504, code="psi_timeout",
            message=f"Google PSI unreachable: {e}",
        ) from e

    lh = data.get("lighthouseResult", {})
    scores = PsiScore(
        performance=_score(lh, "performance"),
        accessibility=_score(lh, "accessibility"),
        best_practices=_score(lh, "best-practices"),
        seo=_score(lh, "seo"),
    )
    cwv = PsiCoreWebVitals(
        lcp_ms=_audit_numeric(lh, "largest-contentful-paint"),
        fid_ms=_audit_numeric(lh, "max-potential-fid"),
        cls=_audit_score_float(lh, "cumulative-layout-shift"),
        fcp_ms=_audit_numeric(lh, "first-contentful-paint"),
        tbt_ms=_audit_numeric(lh, "total-blocking-time"),
        ttfb_ms=_audit_numeric(lh, "server-response-time"),
    )

    # Top 5 opportunities (biggest potential savings)
    opportunities = []
    for audit_id, audit in (lh.get("audits") or {}).items():
        if audit.get("details", {}).get("type") == "opportunity":
            savings_ms = audit.get("details", {}).get("overallSavingsMs", 0)
            if savings_ms and savings_ms > 0:
                opportunities.append({
                    "id": audit_id,
                    "title": audit.get("title", ""),
                    "description": (audit.get("description", "") or "")[:500],
                    "savings_ms": int(savings_ms),
                })
    opportunities.sort(key=lambda x: x["savings_ms"], reverse=True)
    opportunities = opportunities[:5]

    response = PsiCheckResponse(
        url=payload.url,
        strategy=payload.strategy,
        fetched_at=lh.get("fetchTime") or data.get("analysisUTCTimestamp") or "",
        scores=scores,
        core_web_vitals=cwv,
        opportunities=opportunities,
        cached=False,
    )

    # Store in cache (1h TTL)
    try:
        from app.core.redis_client import get_redis
        redis_client = await get_redis()
        import json
        await redis_client.setex(cache_key, 3600, json.dumps(response.model_dump()))
    except Exception:  # noqa: BLE001
        pass

    return response
