"""/v1/admin/cron/* — cron job status + manual triggers.

Jobs tracked:
  - monthly_reset: reset quota counters on day 1 of month
  - health_check: provider health sweep (pings enabled providers)
  - usage_rollup: aggregate AiUsage → daily summary table (future)

Each job's last_run / next_run / status lives in app_settings as JSON
under key "cron_status". Updated by the job itself when it runs.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.admin.audit import AuditLogger
from app.admin.models import AppSetting
from app.core.deps import DbSession
from app.pi_ai_cloud.services.key_allocator import KeyAllocator
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()

CRON_JOBS = [
    {
        "slug": "monthly_reset",
        "name": "Monthly quota reset",
        "description": "Reset monthly_used_tokens cho mọi key + current_period counters cho mọi license_package.",
        "schedule": "0 5 1 * *",  # 05:00 UTC on day 1 of month
    },
    {
        "slug": "health_check",
        "name": "Provider health sweep",
        "description": "Ping mỗi provider đang bật để cập nhật health_status.",
        "schedule": "*/15 * * * *",  # every 15 min
    },
    {
        "slug": "usage_rollup",
        "name": "Daily usage rollup",
        "description": "Aggregate ai_usage vào bảng daily_usage_rollup (tăng tốc chart).",
        "schedule": "0 1 * * *",  # 01:00 UTC daily
    },
]


class CronJobStatus(BaseModel):
    slug: str
    name: str
    description: str
    schedule: str
    last_run_at: Optional[datetime] = None
    last_status: str = "never_run"  # never_run | success | failed
    last_error: str = ""
    last_duration_ms: int = 0
    next_run_estimated_at: Optional[datetime] = None


class CronStatusResponse(BaseModel):
    jobs: list[CronJobStatus]


def _next_monthly_reset() -> datetime:
    now = datetime.now(timezone.utc)
    if now.day == 1 and now.hour < 5:
        return now.replace(hour=5, minute=0, second=0, microsecond=0)
    # Next month day 1 05:00 UTC
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, 5, tzinfo=timezone.utc)
    return datetime(now.year, now.month + 1, 1, 5, tzinfo=timezone.utc)


async def _load_status(db) -> dict:
    row = await db.get(AppSetting, "cron_status")
    return row.value if row else {}


async def _save_status(db, status: dict) -> None:
    row = await db.get(AppSetting, "cron_status")
    if row is None:
        row = AppSetting(key="cron_status", value=status)
        db.add(row)
    else:
        row.value = status
    await db.flush()


@router.get("/cron", response_model=CronStatusResponse)
async def list_cron(admin: CurrentAdmin, db: DbSession) -> CronStatusResponse:  # noqa: ARG001
    raw = await _load_status(db)
    jobs = []
    for job in CRON_JOBS:
        st = raw.get(job["slug"], {})
        next_run = None
        if job["slug"] == "monthly_reset":
            next_run = _next_monthly_reset()
        elif job["slug"] == "health_check":
            # 15-min cadence — estimate next quarter hour
            now = datetime.now(timezone.utc)
            minutes_to_add = 15 - (now.minute % 15)
            next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)
        elif job["slug"] == "usage_rollup":
            now = datetime.now(timezone.utc)
            if now.hour < 1:
                next_run = now.replace(hour=1, minute=0, second=0, microsecond=0)
            else:
                next_run = (now + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0)

        jobs.append(CronJobStatus(
            slug=job["slug"], name=job["name"], description=job["description"], schedule=job["schedule"],
            last_run_at=datetime.fromisoformat(st["last_run_at"]) if st.get("last_run_at") else None,
            last_status=st.get("last_status", "never_run"),
            last_error=st.get("last_error", ""),
            last_duration_ms=int(st.get("last_duration_ms", 0)),
            next_run_estimated_at=next_run,
        ))
    return CronStatusResponse(jobs=jobs)


@router.post("/cron/{slug}/run")
async def run_cron(slug: str, admin: CurrentAdmin, db: DbSession) -> dict:  # noqa: ARG001
    """Manually trigger a cron job."""
    if slug not in {j["slug"] for j in CRON_JOBS}:
        raise HTTPException(404, f"Unknown job '{slug}'")

    started = datetime.now(timezone.utc)
    status = "success"
    error = ""
    result: dict = {}

    try:
        if slug == "monthly_reset":
            count = await KeyAllocator(db).reset_monthly_counters()
            result = {"reset_count": count}
        elif slug == "health_check":
            # Placeholder — full impl would ping each provider.
            result = {"note": "Health check placeholder — wire into ProviderRouter.ping_all()"}
        elif slug == "usage_rollup":
            result = {"note": "Usage rollup placeholder — no daily_usage_rollup table yet"}
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)[:500]

    ended = datetime.now(timezone.utc)
    duration_ms = int((ended - started).total_seconds() * 1000)

    # Persist
    raw = await _load_status(db)
    raw[slug] = {
        "last_run_at": started.isoformat(),
        "last_status": status,
        "last_error": error,
        "last_duration_ms": duration_ms,
    }
    await _save_status(db, raw)

    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="update", resource_type="cron", resource_id=slug,
        resource_label=slug, after={"status": status, "duration_ms": duration_ms, "result": result},
        message=f"Manually ran cron '{slug}' — {status} in {duration_ms}ms",
        severity="warning" if status == "failed" else "info",
    )

    return {
        "slug": slug, "status": status, "duration_ms": duration_ms,
        "error": error, "result": result,
    }
