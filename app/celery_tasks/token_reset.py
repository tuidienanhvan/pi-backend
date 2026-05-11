"""Token reset job - runs daily and resets tenant quotas past their period."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging_conf import get_logger
from app.saas.models import Tenant, Token
from app.saas.tiers import TIER_TOKEN_QUOTA
from app.worker import celery_app

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _quota_for_tier(tier: str) -> int:
    quota = TIER_TOKEN_QUOTA.get(tier, TIER_TOKEN_QUOTA["free"])
    return -1 if quota is None else int(quota)


async def reset_due_tokens(now: datetime | None = None) -> dict[str, int | str]:
    """Reset tokens whose reset window has elapsed."""

    current = _aware(now) or _utc_now()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Token).where(Token.reset_at.is_not(None), Token.reset_at <= current))
        due_tokens = list(result.scalars().all())

        reset_count = 0
        skipped_count = 0
        missing_tenant_count = 0

        for token in due_tokens:
            tenant = await db.get(Tenant, token.tenant_id)
            if tenant is None:
                missing_tenant_count += 1
                continue

            if tenant.tier in {"pro", "max"} and tenant.subscription_status == "active":
                skipped_count += 1
                continue

            token.used_this_month = 0
            token.monthly_quota = _quota_for_tier(tenant.tier)
            token.reset_at = current + timedelta(days=30)
            reset_count += 1

        await db.commit()

    logger.info(
        "token_reset_daily_check",
        extra={
            "reset_count": reset_count,
            "skipped_count": skipped_count,
            "missing_tenant_count": missing_tenant_count,
        },
    )
    return {
        "reset_count": reset_count,
        "skipped_count": skipped_count,
        "missing_tenant_count": missing_tenant_count,
        "timestamp": current.isoformat(),
    }


@celery_app.task(name="token_reset.daily_check")
def daily_token_reset() -> dict[str, int | str]:
    """Celery entrypoint for the daily token reset sweep."""

    return asyncio.run(reset_due_tokens())
