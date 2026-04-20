"""Audit log — model + logger service.

Call `AuditLogger.log(db, actor, action, resource_type, ...)` from any
admin service mutation. Each call inserts one row into `audit_log`.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), default="")

    action: Mapped[str] = mapped_column(String(32), index=True)
    resource_type: Mapped[str] = mapped_column(String(32), index=True)
    resource_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    resource_label: Mapped[str] = mapped_column(String(255), default="")

    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")

    message: Mapped[str] = mapped_column(String(500), default="")
    severity: Mapped[str] = mapped_column(String(16), default="info", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


# ─── Sensitive fields to redact in before/after diffs ──────
_REDACT_FIELDS = {"key_value", "api_key", "password", "password_hash", "token", "secret"}


def _redact(data: Any) -> Any:
    """Recursively redact sensitive keys from JSON-serializable data."""
    if isinstance(data, dict):
        return {k: ("***REDACTED***" if k in _REDACT_FIELDS else _redact(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [_redact(x) for x in data]
    return data


class AuditLogger:
    """Insert audit rows. Safe to call from any service method."""

    @staticmethod
    async def log(
        db: AsyncSession,
        *,
        actor_email: str,
        action: str,
        resource_type: str,
        resource_id: str | int = "",
        resource_label: str = "",
        before: dict | None = None,
        after: dict | None = None,
        message: str = "",
        severity: str = "info",
        actor_id: int | None = None,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
    ) -> None:
        """Record one audit row. Fails silently — never blocks the main action."""
        try:
            entry = AuditLog(
                actor_id=actor_id,
                actor_email=actor_email or "",
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id),
                resource_label=resource_label[:255],
                before=_redact(before) if before else None,
                after=_redact(after) if after else None,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
                request_id=request_id,
                message=message[:500],
                severity=severity,
            )
            db.add(entry)
            await db.flush()
        except Exception:  # noqa: BLE001
            # Audit failures must never break primary writes
            pass

    @staticmethod
    async def list_(
        db: AsyncSession,
        *,
        actor_id: int | None = None,
        action: str = "",
        resource_type: str = "",
        resource_id: str = "",
        severity: str = "",
        q: str = "",
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        qry = select(AuditLog)
        if actor_id is not None:
            qry = qry.where(AuditLog.actor_id == actor_id)
        if action:
            qry = qry.where(AuditLog.action == action)
        if resource_type:
            qry = qry.where(AuditLog.resource_type == resource_type)
        if resource_id:
            qry = qry.where(AuditLog.resource_id == resource_id)
        if severity:
            qry = qry.where(AuditLog.severity == severity)
        if q:
            like = f"%{q}%"
            qry = qry.where(
                (AuditLog.actor_email.ilike(like))
                | (AuditLog.message.ilike(like))
                | (AuditLog.resource_label.ilike(like))
            )
        if from_date:
            qry = qry.where(AuditLog.created_at >= from_date)
        if to_date:
            qry = qry.where(AuditLog.created_at <= to_date)

        total = int((await db.execute(select(func.count()).select_from(qry.subquery()))).scalar_one())
        qry = qry.order_by(AuditLog.id.desc()).limit(limit).offset(offset)
        items = list((await db.execute(qry)).scalars().all())
        return items, total
