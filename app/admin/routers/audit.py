"""Admin audit log query, CSV export, and retention pruning."""

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete

from app.admin.audit import AuditLog, AuditLogger
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


class AuditLogItem(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_email: str
    action: str
    resource_type: str
    resource_id: str
    resource_label: str
    before: Optional[dict] = None
    after: Optional[dict] = None
    ip_address: str
    user_agent: str
    message: str
    severity: str
    created_at: datetime


class AuditLogResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int


class AuditPruneResponse(BaseModel):
    deleted: int
    older_than_days: int
    cutoff: datetime


def _to_item(e: AuditLog) -> AuditLogItem:
    return AuditLogItem(
        id=e.id,
        actor_id=e.actor_id,
        actor_email=e.actor_email,
        action=e.action,
        resource_type=e.resource_type,
        resource_id=e.resource_id,
        resource_label=e.resource_label,
        before=e.before,
        after=e.after,
        ip_address=e.ip_address,
        user_agent=e.user_agent,
        message=e.message,
        severity=e.severity,
        created_at=e.created_at,
    )


async def _query_audit(
    db,
    *,
    actor_id: Optional[int] = None,
    action: str = "",
    resource_type: str = "",
    resource_id: str = "",
    severity: str = "",
    q: str = "",
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    return await AuditLogger.list_(
        db,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        q=q,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )


@router.get("/audit-log", response_model=AuditLogResponse)
async def list_audit(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    actor_id: Optional[int] = Query(None),
    action: str = Query(""),
    resource_type: str = Query(""),
    resource_id: str = Query(""),
    severity: str = Query(""),
    q: str = Query(""),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AuditLogResponse:
    items, total = await _query_audit(
        db,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        q=q,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return AuditLogResponse(items=[_to_item(e) for e in items], total=total, limit=limit, offset=offset)


@router.get("/audit-log/export.csv")
async def export_audit_csv(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    actor_id: Optional[int] = Query(None),
    action: str = Query(""),
    resource_type: str = Query(""),
    resource_id: str = Query(""),
    severity: str = Query(""),
    q: str = Query(""),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
) -> StreamingResponse:
    """Export matching audit rows as CSV for compliance/support review."""
    items, _ = await _query_audit(
        db,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        q=q,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=0,
    )

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "id", "created_at", "actor_id", "actor_email", "action",
        "resource_type", "resource_id", "resource_label", "severity",
        "message", "ip_address", "user_agent",
    ])
    for e in items:
        writer.writerow([
            e.id,
            e.created_at.isoformat() if e.created_at else "",
            e.actor_id or "",
            e.actor_email,
            e.action,
            e.resource_type,
            e.resource_id,
            e.resource_label,
            e.severity,
            e.message,
            e.ip_address,
            e.user_agent,
        ])

    out.seek(0)
    filename = f"audit-log-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/audit-log/prune", response_model=AuditPruneResponse)
async def prune_audit(
    admin: CurrentAdmin,
    db: DbSession,
    older_than_days: int = Query(90, ge=30, le=3650),
) -> AuditPruneResponse:
    """Delete audit rows older than the configured retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    res = await db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    deleted = int(res.rowcount or 0)
    await AuditLogger.log(
        db,
        actor_id=admin.id,
        actor_email=admin.email,
        action="delete",
        resource_type="audit_log",
        resource_id="retention",
        resource_label=f"older_than_{older_than_days}_days",
        after={"deleted": deleted, "cutoff": cutoff.isoformat()},
        message=f"Pruned {deleted} audit log rows older than {older_than_days} days",
        severity="warning",
    )
    return AuditPruneResponse(deleted=deleted, older_than_days=older_than_days, cutoff=cutoff)
