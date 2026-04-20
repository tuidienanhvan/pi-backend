"""/v1/admin/audit-log — query the audit trail."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.admin.audit import AuditLogger
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


@router.get("/audit-log", response_model=AuditLogResponse)
async def list_audit(
    admin: CurrentAdmin, db: DbSession,  # noqa: ARG001
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
    items, total = await AuditLogger.list_(
        db,
        actor_id=actor_id, action=action, resource_type=resource_type,
        resource_id=resource_id, severity=severity, q=q,
        from_date=from_date, to_date=to_date,
        limit=limit, offset=offset,
    )
    return AuditLogResponse(
        items=[AuditLogItem(
            id=e.id, actor_id=e.actor_id, actor_email=e.actor_email,
            action=e.action, resource_type=e.resource_type,
            resource_id=e.resource_id, resource_label=e.resource_label,
            before=e.before, after=e.after,
            ip_address=e.ip_address, user_agent=e.user_agent,
            message=e.message, severity=e.severity, created_at=e.created_at,
        ) for e in items],
        total=total, limit=limit, offset=offset,
    )
