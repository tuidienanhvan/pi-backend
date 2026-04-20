"""QuotaService — per-license Pi-token quota enforcement + reporting.

Flow:
  1. Before completion: check current_period_tokens_used < package.token_quota_monthly
  2. After completion: add_used(license_id, pi_tokens_charged)
  3. On 1st of month: reset_period() — cron
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PiException
from app.pi_ai_cloud.models import AiPackage, AiUsage, LicensePackage


@dataclass
class QuotaCheck:
    ok: bool
    used: int
    limit: int  # 0 = unlimited
    remaining: int  # sys.maxsize when unlimited
    package_slug: str
    allowed_qualities: list[str]


class QuotaExceeded(PiException):
    def __init__(self, used: int, limit: int) -> None:
        super().__init__(
            status_code=402,
            code="quota_exceeded",
            message=f"Token quota exceeded: {used}/{limit} Pi tokens used this period.",
        )


class QuotaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_package(self, license_id: int) -> Optional[tuple[LicensePackage, AiPackage]]:
        q = (
            select(LicensePackage, AiPackage)
            .join(AiPackage, AiPackage.slug == LicensePackage.package_slug)
            .where(LicensePackage.license_id == license_id)
        )
        row = (await self.db.execute(q)).first()
        if row is None:
            return None
        return row[0], row[1]

    async def check(self, license_id: int, *, estimated_tokens: int = 0, quality: str = "balanced") -> QuotaCheck:
        pkg = await self.get_package(license_id)
        if pkg is None:
            # No subscription = no access (except when a trial/default is seeded elsewhere)
            raise PiException(
                status_code=403, code="no_package",
                message="License has no active Pi AI Cloud package.",
            )
        lp, ap = pkg

        if lp.status != "active":
            raise PiException(
                status_code=402, code="subscription_inactive",
                message=f"Subscription is {lp.status}. Renew to continue.",
            )

        if quality not in ap.allowed_qualities:
            raise PiException(
                status_code=403, code="quality_not_allowed",
                message=f"Quality '{quality}' not allowed on {ap.display_name}. Allowed: {ap.allowed_qualities}.",
            )

        limit = int(ap.token_quota_monthly or 0)
        used = int(lp.current_period_tokens_used or 0)
        remaining = (limit - used) if limit > 0 else 10**12  # treat 0 as unlimited

        if limit > 0 and used + max(estimated_tokens, 0) > limit:
            raise QuotaExceeded(used, limit)

        return QuotaCheck(
            ok=True, used=used, limit=limit, remaining=max(0, remaining),
            package_slug=ap.slug, allowed_qualities=list(ap.allowed_qualities),
        )

    async def add_used(self, license_id: int, *, tokens: int) -> None:
        await self.db.execute(
            update(LicensePackage)
            .where(LicensePackage.license_id == license_id)
            .values(
                current_period_tokens_used=LicensePackage.current_period_tokens_used + tokens,
                current_period_requests=LicensePackage.current_period_requests + 1,
                lifetime_tokens_used=LicensePackage.lifetime_tokens_used + tokens,
            )
        )
        await self.db.flush()

    async def reset_period(self, license_id: int | None = None) -> int:
        """Reset current-period counters. If license_id is None, resets ALL."""
        now = datetime.now(timezone.utc)
        q = update(LicensePackage).values(
            current_period_started_at=now,
            current_period_tokens_used=0,
            current_period_requests=0,
        )
        if license_id is not None:
            q = q.where(LicensePackage.license_id == license_id)
        res = await self.db.execute(q)
        await self.db.flush()
        return res.rowcount or 0

    async def daily_usage(self, license_id: int, days: int = 30) -> list[dict]:
        """Return last N days' token consumption for charting."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            select(
                func.date_trunc("day", AiUsage.created_at).label("day"),
                func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0).label("tokens"),
                func.count(AiUsage.id).label("calls"),
            )
            .where(
                AiUsage.license_id == license_id,
                AiUsage.created_at >= since,
                AiUsage.status == "success",
            )
            .group_by("day")
            .order_by("day")
        )
        return [
            {"date": row.day.isoformat() if row.day else None, "tokens": int(row.tokens), "calls": int(row.calls)}
            for row in (await self.db.execute(q)).all()
        ]

    async def usage_by_plugin(self, license_id: int, days: int = 30) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            select(
                AiUsage.source_plugin,
                func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0).label("tokens"),
                func.count(AiUsage.id).label("calls"),
            )
            .where(
                AiUsage.license_id == license_id,
                AiUsage.created_at >= since,
                AiUsage.status == "success",
            )
            .group_by(AiUsage.source_plugin)
            .order_by(func.sum(AiUsage.pi_tokens_charged).desc())
        )
        return [
            {"plugin": row.source_plugin or "direct", "tokens": int(row.tokens), "calls": int(row.calls)}
            for row in (await self.db.execute(q)).all()
        ]
