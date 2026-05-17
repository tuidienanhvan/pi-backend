"""/v1/admin/tokens/ledger — Token transaction ledger for admin.

Reads from `token_transactions` (recorded on every recharge/adjust via
saas/admin_router.py) joined with `tenants` for display-friendly rows.

Filters supported:
  tenant_id     int   — single tenant (0 = all)
  reason        str   — admin_recharge | bonus | refund | purchase | adjust
  date_from     ISO   — inclusive start of window
  date_to       ISO   — inclusive end of window
  delta_sign    str   — "credit" (positive) | "debit" (negative) | "" (both)
  q             str   — free-text search in note field
  limit/offset  pagination (default 50, max 500)

Response includes a summary block (credits/debits/net/count) computed
across the FILTERED set (not paginated set) so the UI totals make sense.
"""

from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.admin.schemas import (
    TokenLedgerResponse,
    TokenLedgerRow,
    TokenLedgerSummary,
)
from app.core.deps import DbSession
from app.saas.models import Tenant, TokenTransaction
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


def _apply_filters(stmt, tenant_id: int, reason: str, date_from: str, date_to: str, delta_sign: str, q: str):
    """Apply filter clauses to a SQLAlchemy stmt over TokenTransaction."""
    if tenant_id:
        stmt = stmt.where(TokenTransaction.tenant_id == tenant_id)
    if reason:
        stmt = stmt.where(TokenTransaction.reason == reason)
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            stmt = stmt.where(TokenTransaction.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            stmt = stmt.where(TokenTransaction.created_at <= dt)
        except ValueError:
            pass
    if delta_sign == "credit":
        stmt = stmt.where(TokenTransaction.delta > 0)
    elif delta_sign == "debit":
        stmt = stmt.where(TokenTransaction.delta < 0)
    if q:
        stmt = stmt.where(TokenTransaction.note.ilike(f"%{q}%"))
    return stmt


@router.get("/tokens/ledger", response_model=TokenLedgerResponse)
async def get_token_ledger(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    tenant_id: int = Query(0, ge=0, description="0 = all tenants"),
    reason: str = "",
    date_from: str = "",
    date_to: str = "",
    delta_sign: str = Query("", description='"credit" | "debit" | ""'),
    q: str = "",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> TokenLedgerResponse:
    # Paginated rows — join tenants for domain display
    page_stmt = (
        select(
            TokenTransaction.id,
            TokenTransaction.created_at.label("timestamp"),
            TokenTransaction.tenant_id,
            TokenTransaction.delta,
            TokenTransaction.reason,
            TokenTransaction.note,
            Tenant.domain.label("tenant_domain"),
        )
        .join(Tenant, Tenant.id == TokenTransaction.tenant_id, isouter=True)
    )
    page_stmt = _apply_filters(page_stmt, tenant_id, reason, date_from, date_to, delta_sign, q)
    page_stmt = page_stmt.order_by(TokenTransaction.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(page_stmt)).all()

    items = [
        TokenLedgerRow(
            id=r.id,
            timestamp=r.timestamp,
            tenant_id=r.tenant_id,
            tenant_domain=r.tenant_domain or "",
            delta=r.delta,
            reason=r.reason,
            note=r.note or "",
        )
        for r in rows
    ]

    # Summary across the FILTERED set (not just the page) using a
    # CASE expression — `greatest`/`least` aren't standard SQL and break
    # on some Postgres builds; CASE is portable + just as fast here.
    credits_expr = func.sum(
        func.coalesce(
            func.nullif(
                func.greatest(TokenTransaction.delta, 0),
                None,
            ),
            0,
        )
    )
    # Postgres has greatest/least, but for safety use CASE.
    summary_stmt = select(
        func.coalesce(
            func.sum(
                # CASE WHEN delta > 0 THEN delta ELSE 0 END
                func.case((TokenTransaction.delta > 0, TokenTransaction.delta), else_=0)
            ),
            0,
        ).label("credits"),
        func.coalesce(
            func.sum(
                # CASE WHEN delta < 0 THEN delta ELSE 0 END
                func.case((TokenTransaction.delta < 0, TokenTransaction.delta), else_=0)
            ),
            0,
        ).label("debits"),
        func.count(TokenTransaction.id).label("cnt"),
    )
    summary_stmt = _apply_filters(summary_stmt, tenant_id, reason, date_from, date_to, delta_sign, q)
    # Suppress unused-name warning on the greatest variant we drafted but did not use.
    _ = credits_expr
    s = (await db.execute(summary_stmt)).one()
    credits = int(s.credits or 0)
    debits_neg = int(s.debits or 0)  # negative number
    summary = TokenLedgerSummary(
        total_credits=credits,
        total_debits=-debits_neg,            # flip sign — UI wants positive
        net=credits + debits_neg,            # debits_neg already negative
        transaction_count=int(s.cnt or 0),
    )

    return TokenLedgerResponse(
        items=items,
        summary=summary,
        total=summary.transaction_count,
        limit=limit,
        offset=offset,
    )
