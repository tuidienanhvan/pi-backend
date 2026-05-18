"""/v1/admin/billing/* — Admin billing/subscription lifecycle (T-20260518-020).

Reads from `licenses` table — joins with Stripe metadata (customer_id,
subscription_id) already stored on License model. Site count from `sites`
relationship.

This is read-only admin observability. Subscription mutations (cancel,
change-tier) go through customer-facing /v1/billing/* endpoints which
handle Stripe API + audit trail.

Endpoints:
  GET /subscriptions          — list w/ filters (status, tier, stripe_linked, q)
  GET /subscriptions/stats    — counters: by-status, by-tier, MRR estimate
"""

from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.admin.schemas import (
    AdminSubscriptionListResponse,
    AdminSubscriptionRow,
    AdminSubscriptionStats,
)
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin
from app.shared.license.models import License, Site

router = APIRouter()


# Canonical USD pricing (matches /v1/tiers/spec). Used for MRR estimate.
_TIER_PRICE_USD = {"free": 0, "pro": 29, "max": 99}


def _row_from_license(lic: License, sites_count: int) -> AdminSubscriptionRow:
    return AdminSubscriptionRow(
        license_id=lic.id,
        license_key=lic.key,
        email=lic.email,
        customer_name=lic.customer_name or "",
        plugin=lic.plugin,
        tier=lic.tier,
        status=lic.status,
        stripe_customer_id=lic.stripe_customer_id,
        stripe_subscription_id=lic.stripe_subscription_id,
        expires_at=lic.expires_at,
        created_at=lic.created_at,
        max_sites=lic.max_sites,
        sites_active=sites_count,
    )


@router.get("/billing/subscriptions", response_model=AdminSubscriptionListResponse)
async def list_subscriptions(
    db: DbSession,
    admin: CurrentAdmin,  # noqa: ARG001
    status: str = Query("", description="active|expired|revoked|suspended"),
    tier: str = Query("", description="free|pro|max|enterprise"),
    stripe_linked: str = Query("", description="yes (has stripe_subscription_id) | no | empty=both"),
    q: str = Query("", description="free-text search in email/license_key/customer_name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AdminSubscriptionListResponse:
    """List license-based subscriptions with billing metadata."""

    stmt = select(License)
    count_stmt = select(func.count(License.id))

    if status:
        stmt = stmt.where(License.status == status)
        count_stmt = count_stmt.where(License.status == status)
    if tier:
        stmt = stmt.where(License.tier == tier)
        count_stmt = count_stmt.where(License.tier == tier)
    if stripe_linked == "yes":
        stmt = stmt.where(License.stripe_subscription_id.is_not(None))
        count_stmt = count_stmt.where(License.stripe_subscription_id.is_not(None))
    elif stripe_linked == "no":
        stmt = stmt.where(License.stripe_subscription_id.is_(None))
        count_stmt = count_stmt.where(License.stripe_subscription_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            License.email.ilike(like) | License.key.ilike(like) | License.customer_name.ilike(like)
        )
        count_stmt = count_stmt.where(
            License.email.ilike(like) | License.key.ilike(like) | License.customer_name.ilike(like)
        )

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(License.created_at.desc()).limit(limit).offset(offset)
    licenses = (await db.execute(stmt)).scalars().all()

    # Batch fetch site counts to avoid N+1
    license_ids = [lic.id for lic in licenses]
    sites_map: dict[int, int] = {}
    if license_ids:
        sites_stmt = (
            select(Site.license_id, func.count(Site.id))
            .where(Site.license_id.in_(license_ids))
            .group_by(Site.license_id)
        )
        for lic_id, cnt in (await db.execute(sites_stmt)).all():
            sites_map[lic_id] = cnt

    items = [_row_from_license(lic, sites_map.get(lic.id, 0)) for lic in licenses]

    # Stats computed across FILTERED set (not just page)
    stats = await _compute_stats(db, status, tier, stripe_linked, q)

    return AdminSubscriptionListResponse(
        items=items,
        stats=stats,
        total=total,
        limit=limit,
        offset=offset,
    )


async def _compute_stats(
    db: DbSession,
    status_filter: str,
    tier_filter: str,
    stripe_linked: str,
    q: str,
) -> AdminSubscriptionStats:
    """Aggregate counters honoring the same filters as the list endpoint."""

    base = select(License.tier, License.status, License.stripe_subscription_id)
    if status_filter:
        base = base.where(License.status == status_filter)
    if tier_filter:
        base = base.where(License.tier == tier_filter)
    if stripe_linked == "yes":
        base = base.where(License.stripe_subscription_id.is_not(None))
    elif stripe_linked == "no":
        base = base.where(License.stripe_subscription_id.is_(None))
    if q:
        like = f"%{q}%"
        base = base.where(
            License.email.ilike(like) | License.key.ilike(like) | License.customer_name.ilike(like)
        )

    rows = (await db.execute(base)).all()

    stats = AdminSubscriptionStats()
    for tier, st, sub_id in rows:
        if st == "active":
            stats.active += 1
        elif st == "expired":
            stats.expired += 1
        elif st == "revoked":
            stats.cancelled += 1
        elif st == "suspended":
            stats.suspended += 1

        if tier == "free":
            stats.free_count += 1
        elif tier == "pro":
            stats.pro_count += 1
        elif tier == "max":
            stats.max_count += 1
        elif tier == "enterprise":
            stats.enterprise_count += 1

        if sub_id:
            stats.stripe_linked += 1
        elif tier in ("pro", "max", "enterprise") and st == "active":
            stats.stripe_unlinked += 1

    # MRR estimate: active pro/max licenses * canonical price
    mrr = stats.pro_count * _TIER_PRICE_USD["pro"] + stats.max_count * _TIER_PRICE_USD["max"]
    stats.estimated_mrr_usd = float(mrr)

    return stats


@router.get("/billing/subscriptions/stats", response_model=AdminSubscriptionStats)
async def billing_stats(
    db: DbSession,
    admin: CurrentAdmin,  # noqa: ARG001
) -> AdminSubscriptionStats:
    """Quick stats card data without paginated list."""
    return await _compute_stats(db, "", "", "", "")


@router.get("/billing/cost-margin")
async def cost_margin(
    db: DbSession,
    admin: CurrentAdmin,  # noqa: ARG001
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Aggregate AI cost vs revenue per license over the last N days.

    Returns per-customer rows with token usage, pi_tokens_charged,
    upstream_cost_cents, and estimated revenue (tier × canonical price).
    """
    from datetime import timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Try to query AI usage table — if it doesn't exist (early stage), graceful fallback
    try:
        from app.pi_ai_cloud.models import AiUsage

        stmt = (
            select(
                License.id,
                License.email,
                License.customer_name,
                License.tier,
                License.plugin,
                func.coalesce(func.sum(AiUsage.input_tokens + AiUsage.output_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0).label("pi_charge"),
                func.coalesce(func.sum(AiUsage.upstream_cost_cents), 0).label("upstream_cost_cents"),
            )
            .join(AiUsage, AiUsage.license_id == License.id, isouter=True)
            .where(
                (AiUsage.created_at >= since) | (AiUsage.created_at.is_(None))
            )
            .where(License.status == "active")
            .group_by(License.id)
            .order_by(
                (func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0)
                 - func.coalesce(func.sum(AiUsage.upstream_cost_cents), 0)).desc()
            )
        )

        rows = (await db.execute(stmt)).all()
    except Exception:
        # AiUsage table might not exist in early-stage deployments
        rows = []

    items = []
    total_revenue = 0
    total_upstream = 0
    total_tokens = 0

    for row in rows:
        monthly_revenue_cents = _TIER_PRICE_USD.get(row.tier, 0) * 100
        upstream = int(row.upstream_cost_cents or 0)
        tokens = int(row.total_tokens or 0)
        margin_cents = monthly_revenue_cents - upstream

        total_revenue += monthly_revenue_cents
        total_upstream += upstream
        total_tokens += tokens

        items.append({
            "license_id": row.id,
            "email": row.email,
            "customer_name": row.customer_name or "",
            "tier": row.tier,
            "plugin": row.plugin,
            "total_tokens": tokens,
            "pi_charge": int(row.pi_charge or 0),
            "upstream_cost_cents": upstream,
            "revenue_cents": monthly_revenue_cents,
            "margin_cents": margin_cents,
        })

    return {
        "window_days": days,
        "summary": {
            "total_revenue_cents": total_revenue,
            "total_upstream_cents": total_upstream,
            "total_margin_cents": total_revenue - total_upstream,
            "margin_percent": round((total_revenue - total_upstream) / max(1, total_revenue) * 100, 1),
            "total_tokens": total_tokens,
            "customer_count": len(items),
        },
        "items": items,
    }
