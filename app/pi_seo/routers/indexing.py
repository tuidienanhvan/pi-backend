"""POST /v1/seo/indexing/submit — submit URL to Google Indexing API.

Attempts real submission via Google Indexing API when service account
credentials are configured (GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON).
Always queues to Redis for audit regardless of submission outcome.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentLicense

router = APIRouter()


class IndexingSubmitRequest(BaseModel):
    url: str
    action: str = Field("URL_UPDATED", pattern="^(URL_UPDATED|URL_DELETED)$")


class IndexingSubmitResponse(BaseModel):
    url: str
    action: str
    status: str  # "submitted" | "queued" | "failed"
    message: str = ""
    submitted_at: datetime


@router.post("/submit", response_model=IndexingSubmitResponse)
async def indexing_submit(
    payload: IndexingSubmitRequest,
    lic: CurrentLicense,
) -> IndexingSubmitResponse:
    """Submit a URL to the Google Indexing API.

    1. Attempt real Google Indexing API submission via service account
    2. Queue to Redis `seo_indexing_queue` for admin audit (always)
    3. Return submission result
    """
    now = datetime.now(timezone.utc)
    status = "queued"
    message = ""

    # --- Step 1: Try real Google Indexing API submission ---
    from app.pi_seo.services.google_indexing import submit_to_google

    result = await submit_to_google(payload.url, payload.action)

    if result.get("submitted"):
        status = "submitted"
        message = "URL submitted to Google Indexing API successfully."
    elif "not configured" in result.get("error", ""):
        status = "queued"
        message = (
            "Google service-account not configured. URL queued for manual submission. "
            "Set GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON to enable real submissions."
        )
    else:
        status = "failed"
        message = f"Google API error: {result.get('error', 'Unknown')}"

    # --- Step 2: Always queue to Redis for audit ---
    try:
        from app.core.redis_client import get_redis
        import json

        redis_client = await get_redis()
        await redis_client.lpush(
            "seo_indexing_queue",
            json.dumps({
                "url": payload.url,
                "action": payload.action,
                "license_id": lic.id,
                "status": status,
                "queued_at": now.isoformat(),
                "google_response": result.get("response") if result.get("submitted") else None,
                "error": result.get("error") if not result.get("submitted") else None,
            }),
        )
        await redis_client.ltrim("seo_indexing_queue", 0, 999)
    except Exception:  # noqa: BLE001
        pass

    return IndexingSubmitResponse(
        url=payload.url,
        action=payload.action,
        status=status,
        message=message,
        submitted_at=now,
    )
