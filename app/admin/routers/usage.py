"""GET /v1/admin/usage — aggregated usage analytics + event drilldown (T-018).

Three endpoints:
  /usage              — aggregate dashboard data (existing, via AdminService)
  /usage/events       — paginated per-request event log (T-018 NEW)
  /usage/aggregate    — pivot rollups by dimension (T-018 NEW)

Event source data: `usage_logs` table (UsageLog model). Joined with
`licenses` for display-friendly license_key + email.

UsageLog does NOT currently store provider_slug / model_id / tenant_id
— those are aggregated by AdminService.usage() via separate joins on
ai_usage table. For per-event drilldown we derive `source` from the
endpoint name prefix (seo_bot.* → seo, chat.* → chat, etc.).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.admin.schemas import (
    AdminUsageAggregateResponse,
    AdminUsageAggregateRow,
    AdminUsageEventRow,
    AdminUsageEventsResponse,
    AdminUsageResponse,
)
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin
from app.shared.license.models import License
from app.shared.usage import UsageLog

router = APIRouter()


def _source_from_endpoint(endpoint: str) -> str:
    """Derive a coarse-grained source bucket from the endpoint string.

    e.g. "seo_bot.generate" → "seo", "chat.reply" → "chat".
    Falls back to the first dot-separated segment.
    """
    if not endpoint:
        return "unknown"
    head = endpoint.split(".", 1)[0]
    return {
        "seo_bot":  "seo",
        "audit":    "seo",
        "schema":   "seo",
        "chat":     "chat",
        "rag":      "chat",
        "post":     "content",
        "lead":     "leads",
        "analytics":"analytics",
    }.get(head, head)


def _apply_filters(
    stmt,
    license_id: int,
    source: str,
    status: str,
    endpoint: str,
    date_from: str,
    date_to: str,
):
    """Apply common filter clauses to a UsageLog stmt."""
    if license_id:
        stmt = stmt.where(UsageLog.license_id == license_id)
    if status:
        stmt = stmt.where(UsageLog.status == status)
    if endpoint:
        # Escape LIKE wildcards in user input to prevent pattern injection.
        safe_ep = endpoint.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(UsageLog.endpoint.ilike(f"%{safe_ep}%", escape="\\"))
    if source:
        # Source = endpoint head prefix; reverse-map by ilike on prefix.
        # e.g. source="seo" matches endpoints starting with seo_bot/audit/schema.
        prefixes = {
            "seo":      ["seo_bot.", "audit.", "schema."],
            "chat":     ["chat.", "rag."],
            "content":  ["post."],
            "leads":    ["lead."],
            "analytics":["analytics."],
        }.get(source, [f"{source}."])
        from sqlalchemy import or_
        stmt = stmt.where(or_(*[UsageLog.endpoint.ilike(f"{p}%") for p in prefixes]))
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            stmt = stmt.where(UsageLog.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            stmt = stmt.where(UsageLog.created_at <= dt)
        except ValueError:
            pass
    return stmt


@router.get("/usage", response_model=AdminUsageResponse)
async def usage(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
    plugin: str = Query(""),
    quality: str = Query(""),
    status: str = Query(""),
) -> AdminUsageResponse:
    data = await AdminService(db).usage(
        days=days, plugin=plugin, quality=quality, status=status,
    )
    return AdminUsageResponse(**data)


@router.get("/usage/events", response_model=AdminUsageEventsResponse)
async def usage_events(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    license_id: int = Query(0, ge=0, description="0 = all licenses"),
    source: str = Query("", description="seo | chat | content | leads | analytics"),
    status: str = Query("", description="success | error | rate_limited"),
    endpoint: str = Query("", description="partial match on endpoint string"),
    date_from: str = "",
    date_to: str = "",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AdminUsageEventsResponse:
    """Per-request drilldown — paginated event log joined with license info."""
    # Page query
    page_stmt = (
        select(
            UsageLog.id,
            UsageLog.created_at.label("timestamp"),
            UsageLog.license_id,
            UsageLog.endpoint,
            UsageLog.site_domain,
            UsageLog.tokens_input,
            UsageLog.tokens_output,
            UsageLog.cost_cents,
            UsageLog.status,
            UsageLog.latency_ms,
            UsageLog.error_message,
            License.key.label("license_key"),
            License.email.label("license_email"),
        )
        .join(License, License.id == UsageLog.license_id, isouter=True)
    )
    page_stmt = _apply_filters(page_stmt, license_id, source, status, endpoint, date_from, date_to)
    page_stmt = page_stmt.order_by(UsageLog.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(page_stmt)).all()

    items = [
        AdminUsageEventRow(
            id=r.id,
            timestamp=r.timestamp,
            license_id=r.license_id,
            license_key=r.license_key or "",
            license_email=r.license_email or "",
            site_domain=r.site_domain or "",
            endpoint=r.endpoint,
            source=_source_from_endpoint(r.endpoint),
            tokens_input=int(r.tokens_input or 0),
            tokens_output=int(r.tokens_output or 0),
            tokens_total=int(r.tokens_input or 0) + int(r.tokens_output or 0),
            cost_cents=int(r.cost_cents or 0),
            status=r.status or "success",
            latency_ms=int(r.latency_ms or 0),
            error_message=r.error_message or "",
        )
        for r in rows
    ]

    # Total count for pagination — same filters, no limit/offset
    count_stmt = select(func.count(UsageLog.id))
    count_stmt = _apply_filters(count_stmt, license_id, source, status, endpoint, date_from, date_to)
    total = (await db.execute(count_stmt)).scalar() or 0

    return AdminUsageEventsResponse(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/usage/aggregate", response_model=AdminUsageAggregateResponse)
async def usage_aggregate(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    dimension: str = Query("source", description="source | license | endpoint | status"),
    days: int = Query(30, ge=1, le=365),
    status: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> AdminUsageAggregateResponse:
    """Pivot rollups for dashboard cards/charts.

    dimension determines how rows are grouped:
      source    — bucket by coarse endpoint prefix (seo/chat/...)
      license   — group by license_id (key shown if known)
      endpoint  — exact endpoint string
      status    — success/error/rate_limited
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = [UsageLog.created_at >= cutoff]
    if status:
        base_filters.append(UsageLog.status == status)

    # Pick group column
    if dimension == "license":
        group_col = func.coalesce(License.key, func.cast(UsageLog.license_id, type_=None)).label("group_key")
        stmt = (
            select(
                License.key.label("group_key"),
                func.count(UsageLog.id).label("calls"),
                func.coalesce(func.sum(UsageLog.tokens_input + UsageLog.tokens_output), 0).label("tokens_total"),
                func.coalesce(func.sum(UsageLog.cost_cents), 0).label("cost_cents"),
                func.coalesce(func.sum(
                    func.case((UsageLog.status == "error", 1), else_=0)
                ), 0).label("error_count"),
                func.coalesce(func.avg(UsageLog.latency_ms), 0).label("avg_latency_ms"),
            )
            .join(License, License.id == UsageLog.license_id, isouter=True)
            .where(*base_filters)
            .group_by(License.key)
        )
    elif dimension == "endpoint":
        stmt = (
            select(
                UsageLog.endpoint.label("group_key"),
                func.count(UsageLog.id).label("calls"),
                func.coalesce(func.sum(UsageLog.tokens_input + UsageLog.tokens_output), 0).label("tokens_total"),
                func.coalesce(func.sum(UsageLog.cost_cents), 0).label("cost_cents"),
                func.coalesce(func.sum(
                    func.case((UsageLog.status == "error", 1), else_=0)
                ), 0).label("error_count"),
                func.coalesce(func.avg(UsageLog.latency_ms), 0).label("avg_latency_ms"),
            )
            .where(*base_filters)
            .group_by(UsageLog.endpoint)
        )
    elif dimension == "status":
        stmt = (
            select(
                UsageLog.status.label("group_key"),
                func.count(UsageLog.id).label("calls"),
                func.coalesce(func.sum(UsageLog.tokens_input + UsageLog.tokens_output), 0).label("tokens_total"),
                func.coalesce(func.sum(UsageLog.cost_cents), 0).label("cost_cents"),
                func.coalesce(func.sum(
                    func.case((UsageLog.status == "error", 1), else_=0)
                ), 0).label("error_count"),
                func.coalesce(func.avg(UsageLog.latency_ms), 0).label("avg_latency_ms"),
            )
            .where(*base_filters)
            .group_by(UsageLog.status)
        )
    else:
        # default = source: group by derived prefix. Since source is computed
        # in Python, we group by endpoint then re-bucket in code.
        stmt = (
            select(
                UsageLog.endpoint.label("group_key"),
                func.count(UsageLog.id).label("calls"),
                func.coalesce(func.sum(UsageLog.tokens_input + UsageLog.tokens_output), 0).label("tokens_total"),
                func.coalesce(func.sum(UsageLog.cost_cents), 0).label("cost_cents"),
                func.coalesce(func.sum(
                    func.case((UsageLog.status == "error", 1), else_=0)
                ), 0).label("error_count"),
                func.coalesce(func.avg(UsageLog.latency_ms), 0).label("avg_latency_ms"),
            )
            .where(*base_filters)
            .group_by(UsageLog.endpoint)
        )

    stmt = stmt.order_by(func.count(UsageLog.id).desc()).limit(limit)
    raw_rows = (await db.execute(stmt)).all()

    # Re-bucket source dimension in Python
    if dimension == "source":
        buckets: dict[str, dict] = {}
        for r in raw_rows:
            src = _source_from_endpoint(r.group_key or "")
            b = buckets.setdefault(src, {"calls": 0, "tokens": 0, "cost": 0, "errors": 0, "lat_sum": 0, "lat_n": 0})
            b["calls"] += int(r.calls or 0)
            b["tokens"] += int(r.tokens_total or 0)
            b["cost"] += int(r.cost_cents or 0)
            b["errors"] += int(r.error_count or 0)
            b["lat_sum"] += int(r.avg_latency_ms or 0) * int(r.calls or 0)
            b["lat_n"] += int(r.calls or 0)
        rows = [
            AdminUsageAggregateRow(
                group_key=k,
                calls=v["calls"],
                tokens_total=v["tokens"],
                cost_cents=v["cost"],
                error_count=v["errors"],
                avg_latency_ms=int(v["lat_sum"] / v["lat_n"]) if v["lat_n"] else 0,
            )
            for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]["calls"])
        ]
    else:
        rows = [
            AdminUsageAggregateRow(
                group_key=str(r.group_key or "unknown"),
                calls=int(r.calls or 0),
                tokens_total=int(r.tokens_total or 0),
                cost_cents=int(r.cost_cents or 0),
                error_count=int(r.error_count or 0),
                avg_latency_ms=int(r.avg_latency_ms or 0),
            )
            for r in raw_rows
        ]

    total_calls = sum(r.calls for r in rows)
    total_tokens = sum(r.tokens_total for r in rows)
    total_cost = sum(r.cost_cents for r in rows)

    return AdminUsageAggregateResponse(
        dimension=dimension,
        rows=rows,
        total_calls=total_calls,
        total_tokens=total_tokens,
        total_cost_cents=total_cost,
    )
