"""SEO Bot endpoints — AI-powered title/desc/OG generation."""

import time

from fastapi import APIRouter

from app.core.deps import DbSession, RateLimitedLicense
from app.pi_seo.schemas import (
    SeoBotBulkRequest,
    SeoBotBulkResponse,
    SeoBotGenerateRequest,
    SeoBotGenerateResponse,
)
from app.shared.license.service import LicenseService
from app.pi_seo.services.seo_bot import SeoBotService

router = APIRouter()
_svc = SeoBotService()


@router.post("/generate", response_model=SeoBotGenerateResponse)
async def generate(
    req: SeoBotGenerateRequest,
    lic: RateLimitedLicense,
    db: DbSession,
) -> SeoBotGenerateResponse:
    """Generate N variants of SEO title + meta description.

    The Pi SEO plugin should call this instead of computing locally —
    the prompt engineering is our IP and stays server-side.
    """
    started = time.perf_counter()
    svc_lic = LicenseService(db)
    domain = svc_lic._normalise_domain(req.site_url)

    try:
        variants, meta = await _svc.generate(req)
    except Exception as e:
        latency = int((time.perf_counter() - started) * 1000)
        await svc_lic.log_usage(
            lic,
            "seo_bot.generate",
            site_domain=domain,
            status="error",
            latency_ms=latency,
            error_message=str(e)[:500],
        )
        raise

    latency = int((time.perf_counter() - started) * 1000)
    await svc_lic.log_usage(
        lic,
        "seo_bot.generate",
        site_domain=domain,
        tokens_input=meta["input_tokens"],
        tokens_output=meta["output_tokens"],
        latency_ms=latency,
    )

    return SeoBotGenerateResponse(
        success=True,
        variants=variants,
        tokens_used=meta["input_tokens"] + meta["output_tokens"],
        model=meta["model"],
    )


@router.post("/bulk", response_model=SeoBotBulkResponse)
async def bulk_generate(
    req: SeoBotBulkRequest,
    lic: RateLimitedLicense,
    db: DbSession,  # noqa: ARG001
) -> SeoBotBulkResponse:
    """Queue bulk AI generation — runs in Celery worker, returns task_id."""
    if lic.tier not in ("pro", "agency"):
        from app.core.exceptions import LicenseInvalid

        raise LicenseInvalid("Bulk generation requires Pro or Agency tier")

    from app.shared.tasks import seo_bot_bulk_generate

    task = seo_bot_bulk_generate.delay(lic.id, req.posts)
    return SeoBotBulkResponse(
        success=True,
        task_id=task.id,
        queued=len(req.posts),
        message=f"Queued {len(req.posts)} posts — check /v1/seo-bot/status/{task.id}",
    )


@router.get("/status/{task_id}")
async def task_status(task_id: str, lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    """Check status of a queued bulk task."""
    from app.worker import celery_app

    async_result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "state": async_result.state,
        "ready": async_result.ready(),
        "result": async_result.result if async_result.ready() else None,
    }
