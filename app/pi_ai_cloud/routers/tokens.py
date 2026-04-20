"""Token wallet + top-up + webhook endpoints."""

from fastapi import APIRouter, Header, Request

from app.core.deps import CurrentLicense, DbSession
from app.core.exceptions import PiException
from app.core.logging_conf import get_logger
from app.pi_ai_cloud.schemas import (
    LedgerEntry,
    LedgerResponse,
    TopupCheckoutRequest,
    TopupCheckoutResponse,
    WalletResponse,
)
from app.pi_ai_cloud.services.billing import StripeBilling
from app.pi_ai_cloud.services.wallet import TOPUP_PACKS, WalletService

logger = get_logger(__name__)
router = APIRouter()


# ── Wallet ──────────────────────────────────────────────────


@router.get("/wallet", response_model=WalletResponse)
async def get_wallet(lic: CurrentLicense, db: DbSession) -> WalletResponse:
    svc = WalletService(db)
    w = await svc.get_or_create(lic)
    return WalletResponse(
        balance=w.balance,
        lifetime_topup=w.lifetime_topup,
        lifetime_spend=w.lifetime_spend,
        daily_limit=w.daily_limit,
        last_activity_at=w.last_activity_at,
    )


@router.get("/ledger", response_model=LedgerResponse)
async def get_ledger(
    lic: CurrentLicense,
    db: DbSession,
    limit: int = 50,
    offset: int = 0,
) -> LedgerResponse:
    limit = max(1, min(200, limit))
    svc = WalletService(db)
    w = await svc.get_or_create(lic)
    entries = await svc.list_ledger(w, limit=limit + 1, offset=offset)
    has_more = len(entries) > limit
    return LedgerResponse(
        entries=[
            LedgerEntry(
                id=e.id,
                op=e.op,
                delta=e.delta,
                balance_after=e.balance_after,
                reference_type=e.reference_type,
                note=e.note,
                created_at=e.created_at,
            )
            for e in entries[:limit]
        ],
        has_more=has_more,
    )


# ── Top-up (Stripe Checkout) ────────────────────────────────


@router.post("/topup/checkout", response_model=TopupCheckoutResponse)
async def topup_checkout(
    req: TopupCheckoutRequest,
    lic: CurrentLicense,
) -> TopupCheckoutResponse:
    billing = StripeBilling()
    result = await billing.create_checkout_session(
        pack=req.pack,
        license_id=lic.id,
        success_url=req.success_url,
        cancel_url=req.cancel_url,
    )
    return TopupCheckoutResponse(**result)


@router.get("/topup/packs")
async def list_packs() -> dict:
    """List available token packs + pricing."""
    return {
        "packs": [
            {
                "id": pack_id,
                "tokens": tokens,
                "price_cents": price_cents,
                "price_usd": price_cents / 100,
            }
            for pack_id, (tokens, price_cents) in TOPUP_PACKS.items()
        ]
    }


# ── Stripe webhook (no auth — verified by signature) ─────────


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_signature: str = Header(""),
) -> dict:
    billing = StripeBilling()
    payload = await request.body()

    try:
        event = billing.verify_webhook(payload, stripe_signature)
    except PiException:
        raise

    event_type = event.get("type", "")
    if event_type != "checkout.session.completed":
        return {"received": True, "ignored": event_type}

    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {})
    license_id = int(metadata.get("license_id", 0))
    tokens = int(metadata.get("tokens", 0))
    session_id = str(data.get("id", ""))

    if not license_id or tokens <= 0:
        logger.error("webhook_missing_metadata", extra={"session_id": session_id})
        return {"received": True, "error": "missing metadata"}

    # Idempotency — check if we've already credited this session
    from sqlalchemy import select

    from app.pi_ai_cloud.models import TokenLedger
    from app.shared.license.models import License

    existing = await db.execute(
        select(TokenLedger).where(
            TokenLedger.reference_id == session_id,
            TokenLedger.reference_type == "stripe_payment",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return {"received": True, "duplicate": True}

    lic = await db.get(License, license_id)
    if lic is None:
        return {"received": True, "error": "license not found"}

    svc = WalletService(db)
    wallet = await svc.get_or_create(lic)
    await svc.topup(
        wallet,
        tokens,
        reference_type="stripe_payment",
        reference_id=session_id,
        note=f"Pack {metadata.get('pack', '?')}",
    )

    logger.info(
        "wallet_topup",
        extra={"license_id": license_id, "tokens": tokens, "session_id": session_id},
    )
    return {"received": True, "credited": tokens}


# NOTE: /providers endpoint REMOVED from customer API.
# Upstream routing is Pi's internal concern — customers never know which
# provider served their request. Admin sees full provider list at
# /v1/admin/providers (requires admin JWT).
