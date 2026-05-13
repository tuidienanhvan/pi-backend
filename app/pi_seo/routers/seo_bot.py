"""SEO Bot endpoints powered by Pi AI Cloud."""

import time

from fastapi import APIRouter

from app.core.deps import DbSession, RateLimitedLicense
from app.pi_ai_cloud.services.completion import CompletionService
from app.pi_seo.schemas import (
    SeoBotBulkRequest,
    SeoBotBulkResponse,
    SeoBotGenerateRequest,
    SeoBotGenerateResponse,
)
from app.pi_seo.services.seo_bot import SeoBotService
from app.shared.license.service import LicenseService

router = APIRouter()


@router.post("/generate", response_model=SeoBotGenerateResponse)
async def generate(
    req: SeoBotGenerateRequest,
    lic: RateLimitedLicense,
    db: DbSession,
) -> SeoBotGenerateResponse:
    started = time.perf_counter()
    license_service = LicenseService(db)
    domain = license_service._normalise_domain(req.site_url)
    service = SeoBotService(CompletionService(db))

    try:
        variants, meta = await service.generate(lic, req)
    except Exception as e:
        latency = int((time.perf_counter() - started) * 1000)
        await license_service.log_usage(
            lic,
            "seo_bot.generate",
            site_domain=domain,
            status="error",
            latency_ms=latency,
            error_message=str(e)[:500],
        )
        raise

    return SeoBotGenerateResponse(
        success=True,
        variants=variants,
        tokens_used=meta["pi_tokens_charged"],
        model=meta["model"],
    )


@router.post("/bulk", response_model=SeoBotBulkResponse)
async def bulk_generate(
    req: SeoBotBulkRequest,
    lic: RateLimitedLicense,
    db: DbSession,  # noqa: ARG001
) -> SeoBotBulkResponse:
    if lic.tier not in ("pro", "max", "enterprise"):
        from app.core.exceptions import LicenseInvalid

        raise LicenseInvalid("Bulk generation requires Pro or Max tier")

    from app.shared.tasks import seo_bot_bulk_generate

    task = seo_bot_bulk_generate.delay(lic.id, req.posts)
    return SeoBotBulkResponse(
        success=True,
        task_id=task.id,
        queued=len(req.posts),
        message=f"Queued {len(req.posts)} posts - check /v1/seo-bot/status/{task.id}",
    )


@router.get("/status/{task_id}")
async def task_status(task_id: str, lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    from app.worker import celery_app

    async_result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "state": async_result.state,
        "ready": async_result.ready(),
        "result": async_result.result if async_result.ready() else None,
    }
