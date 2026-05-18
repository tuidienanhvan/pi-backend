"""/v1/admin/cron/* — cron job status + manual triggers.

Jobs tracked:
  - monthly_reset: reset quota counters on day 1 of month
  - health_check: provider health sweep (pings enabled providers)
  - usage_rollup: aggregate AiUsage → daily summary table (future)

Each job's last_run / next_run / status lives in app_settings as JSON
under key "cron_status". Updated by the job itself when it runs.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.admin.audit import AuditLogger
from app.admin.models import AppSetting
from app.core.deps import DbSession
from app.pi_ai_cloud.services.key_allocator import KeyAllocator
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()

# Static secret used by GitHub Actions / external schedulers to trigger crons
# without needing a rotating admin JWT. Set CRON_SECRET in env.
# Empty/unset = header auth disabled (only admin JWT path allowed).
CRON_SECRET = os.getenv("CRON_SECRET", "")

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


class CronRunHistoryItem(BaseModel):
    slug: str
    status: str
    started_at: datetime
    duration_ms: int = 0
    actor: str = ""
    error: str = ""
    result: dict = {}


class CronRunHistoryResponse(BaseModel):
    items: list[CronRunHistoryItem]
    total: int


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


@router.post("/cron/{slug}/run-public")
async def run_cron_public(
    slug: str,
    db: DbSession,
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
) -> dict:
    """External trigger (GitHub Actions, Vercel Cron, etc.) — uses static secret.

    Requires CRON_SECRET env var to be set. Compares with constant-time check.
    Does NOT write to audit_log (no admin actor) but updates cron_status.
    """
    if not CRON_SECRET:
        raise HTTPException(503, "External cron trigger disabled (CRON_SECRET not set)")
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, CRON_SECRET):
        raise HTTPException(401, "Invalid X-Cron-Secret")
    return await _execute_cron(slug, db, actor_label="external-cron")


@router.post("/cron/{slug}/run")
async def run_cron(slug: str, admin: CurrentAdmin, db: DbSession) -> dict:
    """Admin manual trigger (UI). Writes audit log."""
    result = await _execute_cron(slug, db, actor_label=f"admin:{admin.email}")
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="update", resource_type="cron", resource_id=slug,
        resource_label=slug, after={"status": result["status"], "duration_ms": result["duration_ms"]},
        message=f"Manually ran cron '{slug}' — {result['status']} in {result['duration_ms']}ms",
        severity="warning" if result["status"] == "failed" else "info",
    )
    return result


@router.get("/cron/{slug}/history", response_model=CronRunHistoryResponse)
async def cron_history(
    slug: str,
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    limit: int = 50,
) -> CronRunHistoryResponse:
    """Return recent run history for one cron job.

    Stored in app_settings.cron_status["_history"] to avoid adding a table
    while still making manual/external runs observable from Admin.
    """
    if slug not in {j["slug"] for j in CRON_JOBS}:
        raise HTTPException(404, f"Unknown job '{slug}'")

    raw = await _load_status(db)
    history = raw.get("_history", {}).get(slug, [])
    safe_limit = max(1, min(int(limit or 50), 200))
    items = []
    for row in history[:safe_limit]:
        started = row.get("started_at") or row.get("last_run_at")
        if not started:
            continue
        items.append(CronRunHistoryItem(
            slug=slug,
            status=row.get("status", "unknown"),
            started_at=datetime.fromisoformat(started),
            duration_ms=int(row.get("duration_ms", 0)),
            actor=row.get("actor", ""),
            error=row.get("error", ""),
            result=row.get("result", {}) if isinstance(row.get("result"), dict) else {},
        ))
    return CronRunHistoryResponse(items=items, total=len(history))


async def _execute_cron(slug: str, db, *, actor_label: str) -> dict:
    """Shared cron executor — used by both /run (admin) and /run-public (external)."""
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
            # Provider health survey — aggregate status + mark stale providers
            # as degraded. Real per-provider API ping would burn tokens, so we
            # observe state instead. Providers self-update via mark_success /
            # mark_failure during real traffic; this job catches abandoned ones.
            from sqlalchemy import select
            from datetime import timedelta
            from app.pi_ai_cloud.models import AiProvider

            stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            providers = (await db.execute(
                select(AiProvider).where(AiProvider.is_enabled.is_(True))
            )).scalars().all()

            stale_count = 0
            counts = {"healthy": 0, "degraded": 0, "down": 0, "unknown": 0}
            for p in providers:
                if (
                    p.health_status == "healthy"
                    and p.last_success_at
                    and p.last_success_at < stale_cutoff
                ):
                    p.health_status = "degraded"
                    stale_count += 1
                counts[p.health_status] = counts.get(p.health_status, 0) + 1

            if stale_count:
                await db.flush()

            result = {
                "providers_surveyed": len(providers),
                "by_status": counts,
                "marked_stale": stale_count,
            }
        elif slug == "usage_rollup":
            # Last-24h aggregate from ai_usage table (no migration needed —
            # compute on demand instead of materialised daily_usage_rollup).
            from sqlalchemy import select, func as sa_func
            from datetime import timedelta
            from app.pi_ai_cloud.models import AiUsage

            since = datetime.now(timezone.utc) - timedelta(days=1)
            row = (await db.execute(
                select(
                    sa_func.count(AiUsage.id),
                    sa_func.coalesce(sa_func.sum(AiUsage.input_tokens + AiUsage.output_tokens), 0),
                    sa_func.coalesce(sa_func.sum(AiUsage.pi_tokens_charged), 0),
                    sa_func.coalesce(sa_func.sum(AiUsage.upstream_cost_cents), 0),
                ).where(AiUsage.created_at >= since)
            )).one()

            result = {
                "window": "last_24h",
                "calls": int(row[0] or 0),
                "upstream_tokens": int(row[1] or 0),
                "pi_tokens_charged": int(row[2] or 0),
                "upstream_cost_cents": int(row[3] or 0),
            }
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
        "last_actor": actor_label,
    }
    history_root = raw.setdefault("_history", {})
    job_history = history_root.setdefault(slug, [])
    job_history.insert(0, {
        "slug": slug,
        "status": status,
        "started_at": started.isoformat(),
        "duration_ms": duration_ms,
        "actor": actor_label,
        "error": error,
        "result": result,
    })
    history_root[slug] = job_history[:200]
    await _save_status(db, raw)

    return {
        "slug": slug, "status": status, "duration_ms": duration_ms,
        "error": error, "result": result,
    }
