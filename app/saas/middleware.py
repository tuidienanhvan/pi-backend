"""Tier and quota enforcement dependencies for tenant-scoped endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select

from app.core.deps import DbSession
from app.saas.deps import TenantContext, get_tenant
from app.saas.models import Token
from app.saas.tiers import TIER_FEATURES, TIER_TOKEN_QUOTA, normalize_tier


def _features_for_context(ctx: TenantContext) -> list[str]:
    tier = normalize_tier(ctx.tenant.tier)
    tier_features = list(TIER_FEATURES.get(tier, []))
    custom_features = list(ctx.features or [])
    return list(dict.fromkeys([*tier_features, *custom_features]))


def require_feature(feature: str):
    """FastAPI dependency: returns tenant context or raises 403 with upgrade metadata."""

    async def dependency(ctx: Annotated[TenantContext, Depends(get_tenant)]) -> TenantContext:
        features = _features_for_context(ctx)
        if "*" in features or feature in features:
            return ctx

        raise HTTPException(
            status_code=403,
            detail={
                "error": "feature_not_available",
                "message": f'Tính năng "{feature}" không có trong gói {ctx.tenant.tier}. Vui lòng nâng cấp.',
                "required_feature": feature,
                "current_tier": ctx.tenant.tier,
                "upgrade_url": "/pricing",
            },
        )

    return dependency


def require_quota(estimated_tokens: int = 0):
    """FastAPI dependency: returns tenant context or raises 429 when monthly quota is exhausted."""

    async def dependency(
        ctx: Annotated[TenantContext, Depends(get_tenant)],
        db: DbSession,
    ) -> TenantContext:
        tier_quota = TIER_TOKEN_QUOTA.get(normalize_tier(ctx.tenant.tier), TIER_TOKEN_QUOTA["free"])
        if tier_quota is None:
            return ctx

        result = await db.execute(select(Token).where(Token.tenant_id == ctx.tenant_id))
        token = result.scalar_one_or_none()
        if token is None:
            return ctx

        monthly_quota = token.monthly_quota
        if monthly_quota < 0:
            return ctx

        remaining = monthly_quota - token.used_this_month
        if remaining < estimated_tokens:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "quota_exceeded",
                    "message": (
                        f"Đã hết token tháng này ({token.used_this_month}/{monthly_quota}). "
                        "Nạp thêm hoặc nâng cấp."
                    ),
                    "used": token.used_this_month,
                    "quota": monthly_quota,
                    "remaining": max(remaining, 0),
                    "topup_url": "/app/wallet/topup",
                },
            )

        return ctx

    return dependency
