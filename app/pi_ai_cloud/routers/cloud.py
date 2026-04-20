"""/v1/cloud/* — customer-facing Pi AI Cloud endpoints.

Customer sees:
  - Their active package + quota used/remaining
  - Daily usage chart (last 30 days)
  - Per-plugin breakdown
Customer does NOT see: keys, provider names, upstream cost.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentLicense, DbSession
from app.pi_ai_cloud.models import AiPackage, LicensePackage
from app.pi_ai_cloud.services.quota import QuotaService

router = APIRouter()


class CustomerPackageResponse(BaseModel):
    package_slug: str
    package_name: str
    description: str = ""
    token_quota_monthly: int
    allowed_qualities: list[str]
    status: str
    activated_at: datetime
    renews_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    current_period_started_at: datetime
    current_period_tokens_used: int
    current_period_remaining: int
    current_period_requests: int
    lifetime_tokens_used: int


class CustomerUsageBreakdown(BaseModel):
    daily: list[dict]  # [{date, tokens, calls}, ...]
    by_plugin: list[dict]  # [{plugin, tokens, calls}, ...]


@router.get("/package", response_model=Optional[CustomerPackageResponse])
async def get_my_package(lic: CurrentLicense, db: DbSession) -> Optional[CustomerPackageResponse]:
    row = (await db.execute(
        select(LicensePackage, AiPackage)
        .join(AiPackage, AiPackage.slug == LicensePackage.package_slug)
        .where(LicensePackage.license_id == lic.id)
    )).first()
    if row is None:
        return None
    lp, ap = row
    limit = int(ap.token_quota_monthly or 0)
    used = int(lp.current_period_tokens_used or 0)
    remaining = max(0, limit - used) if limit > 0 else 10**12
    return CustomerPackageResponse(
        package_slug=ap.slug,
        package_name=ap.display_name,
        description=ap.description or "",
        token_quota_monthly=limit,
        allowed_qualities=list(ap.allowed_qualities or []),
        status=lp.status,
        activated_at=lp.activated_at,
        renews_at=lp.renews_at,
        expires_at=lp.expires_at,
        current_period_started_at=lp.current_period_started_at,
        current_period_tokens_used=used,
        current_period_remaining=remaining,
        current_period_requests=int(lp.current_period_requests or 0),
        lifetime_tokens_used=int(lp.lifetime_tokens_used or 0),
    )


@router.get("/usage", response_model=CustomerUsageBreakdown)
async def get_my_usage(lic: CurrentLicense, db: DbSession, days: int = 30) -> CustomerUsageBreakdown:
    svc = QuotaService(db)
    daily = await svc.daily_usage(lic.id, days=days)
    by_plugin = await svc.usage_by_plugin(lic.id, days=days)
    return CustomerUsageBreakdown(daily=daily, by_plugin=by_plugin)
