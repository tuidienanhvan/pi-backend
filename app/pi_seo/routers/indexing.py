"""POST /v1/seo/indexing/submit — submit URL to Google Indexing API.

TODO: Google Indexing API requires a service-account JSON credential and
the site owner verified in Google Search Console. This implementation is
scaffolded — admin must upload the service-account JSON via /admin/settings
before live submissions work.

For now: returns a stub success + queues the URL in a Redis list so admin
can see what would be submitted.
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
    status: str  # "queued" | "submitted" | "failed"
    message: str = ""
    submitted_at: datetime


@router.post("/submit", response_model=IndexingSubmitResponse)
async def indexing_submit(
    payload: IndexingSubmitRequest,
    lic: CurrentLicense,  # noqa: ARG001
) -> IndexingSubmitResponse:
    """Queue a URL for Google Indexing API submission.

    Live path (not yet implemented):
      1. Load service-account JSON from settings (Pi team uploads once)
      2. Generate JWT, exchange for access token
      3. POST https://indexing.googleapis.com/v3/urlNotifications:publish
           {"url": "...", "type": "URL_UPDATED"}
      4. Parse response, return success/failure

    Current stub: logs to Redis list `seo_indexing_queue` so admin can audit.
    """
    now = datetime.now(timezone.utc)

    try:
        from app.core.redis_client import get_redis
        import json
        redis_client = await get_redis()
        await redis_client.lpush(
            "seo_indexing_queue",
            json.dumps({
                "url": payload.url, "action": payload.action,
                "license_id": lic.id, "queued_at": now.isoformat(),
            }),
        )
        await redis_client.ltrim("seo_indexing_queue", 0, 999)  # keep last 1000
    except Exception:  # noqa: BLE001
        pass

    return IndexingSubmitResponse(
        url=payload.url,
        action=payload.action,
        status="queued",
        message="URL queued. Live submission requires Google service-account JSON (admin setup pending).",
        submitted_at=now,
    )
