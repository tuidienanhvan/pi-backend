"""Pi Analytics — event ingestion + aggregated reports (optional Pro backend)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.deps import DbSession, CurrentLicense

router = APIRouter()


class BatchEvent(BaseModel):
    event_name: str
    page_url: str = ""
    page_id: int = 0
    referrer: str = ""
    device: str = ""
    ts: datetime | None = None


class IngestRequest(BaseModel):
    events: list[BatchEvent]


@router.post("/ingest")
async def ingest(req: IngestRequest, lic: CurrentLicense, db: DbSession) -> dict:  # noqa: ARG001
    """Accept batch events from plugin for centralised analytics (Pro tier).
    Placeholder — Phase 4 will persist to `analytics_events_remote`.
    """
    return {"success": True, "accepted": len(req.events)}


@router.get("/report/pageviews")
async def pageviews(
    lic: CurrentLicense,
    days: int = Query(30, ge=1, le=365),
) -> dict:  # noqa: ARG001
    """Return aggregated pageviews for this license's sites (Phase 4)."""
    return {
        "success": True,
        "days": days,
        "total_pageviews": 0,
        "note": "Remote analytics storage — Phase 4.",
    }


@router.get("/status")
async def status(lic: CurrentLicense) -> dict:
    return {"plugin": "pi-analytics", "tier": lic.tier, "endpoints": ["ingest", "report/pageviews"]}
