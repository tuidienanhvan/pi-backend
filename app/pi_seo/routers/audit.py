"""Audit endpoints — 100-point scoring + content analysis."""

import time

from fastapi import APIRouter

from app.core.deps import DbSession, RateLimitedLicense
from app.pi_seo.schemas import (
    AuditRunRequest,
    AuditRunResponse,
    ContentAnalyzeRequest,
    ContentAnalyzeResponse,
)
from app.shared.license.service import LicenseService
from app.pi_seo.services.scorer import analyze_content, run_audit

router = APIRouter()


@router.post("/run", response_model=AuditRunResponse)
async def audit_run(
    req: AuditRunRequest,
    lic: RateLimitedLicense,
    db: DbSession,
) -> AuditRunResponse:
    """Run the 100-point audit on raw HTML + meta."""
    started = time.perf_counter()
    result = run_audit(
        title=req.title,
        meta_description=req.meta_description,
        focus_keyword=req.focus_keyword,
        html=req.html,
        url=req.url,
    )

    svc = LicenseService(db)
    await svc.log_usage(
        lic,
        "audit.run",
        site_domain=svc._normalise_domain(req.site_url),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return result


@router.post("/content", response_model=ContentAnalyzeResponse)
async def content_analysis(
    req: ContentAnalyzeRequest,
    lic: RateLimitedLicense,
    db: DbSession,
) -> ContentAnalyzeResponse:
    """Readability + keyword density analysis (no AI, fast)."""
    started = time.perf_counter()
    result = analyze_content(
        content=req.content,
        focus_keyword=req.focus_keyword,
        language=req.language,
    )

    svc = LicenseService(db)
    await svc.log_usage(
        lic,
        "audit.content_analyze",
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return ContentAnalyzeResponse(success=True, **result)
