"""Tenant subscription billing endpoints and Stripe webhook."""

from __future__ import annotations

import os
from typing import Annotated, Awaitable, Callable

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.schemas import (
    CancelSubscriptionResponse,
    ChangeTierRequest,
    ChangeTierResponse,
    SubscribeRequest,
    SubscribeResponse,
    SubscriptionStatusResponse,
)
from app.billing.stripe_subscription import (
    StripeSubscriptionService,
    handle_checkout_completed,
    handle_invoice_failed,
    handle_invoice_paid,
    handle_subscription_created,
    handle_subscription_deleted,
    handle_subscription_updated,
)
from app.core.db import get_db
from app.core.logging_conf import get_logger
from app.saas.deps import TenantContext, get_tenant

logger = get_logger(__name__)
router = APIRouter()

WebhookHandler = Callable[[object, AsyncSession], Awaitable[None]]

WEBHOOK_HANDLERS: dict[str, WebhookHandler] = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.payment_succeeded": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_failed,
}


@router.post("/subscribe/checkout", response_model=SubscribeResponse)
async def create_subscription_checkout(
    body: SubscribeRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant)],
) -> SubscribeResponse:
    url = await StripeSubscriptionService.create_checkout(
        ctx.tenant,
        body.tier,
        str(body.success_url),
        str(body.cancel_url),
    )
    return SubscribeResponse(checkout_url=url)


@router.post("/subscribe/simulate-success", include_in_schema=False)
async def simulate_subscription_success(
    body: SubscribeRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    """Bypass Stripe and activate a tier immediately (for demo/dev only).

    Returns 404 in production to hide the endpoint entirely.
    """
    from app.core.config import settings as _settings
    if _settings.app_env == "production":
        raise HTTPException(404, "Not found")
    if os.getenv("APP_ENV") not in ("development", "test") and os.getenv("DEMO_MODE") != "true":
        raise HTTPException(403, "Simulation mode is not enabled")

    # Mock Stripe Session object for handle_checkout_completed
    mock_session = {
        "subscription": f"sub_mock_{ctx.tenant.id}_{body.tier}",
        "metadata": {"tenant_id": str(ctx.tenant.id), "target_tier": body.tier},
        "client_reference_id": str(ctx.tenant.id),
    }
    await handle_checkout_completed(mock_session, db)
    await db.commit()
    return {"success": True}


@router.patch("/subscribe/change-tier", response_model=ChangeTierResponse)
async def change_tier(
    body: ChangeTierRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeTierResponse:
    try:
        await StripeSubscriptionService.upgrade_or_downgrade(ctx.tenant, body.new_tier, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ChangeTierResponse(success=True, new_tier=body.new_tier)


@router.post("/subscribe/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    ctx: Annotated[TenantContext, Depends(get_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CancelSubscriptionResponse:
    await StripeSubscriptionService.cancel(ctx.tenant, db)
    return CancelSubscriptionResponse(success=True)


@router.get("/subscribe/status", response_model=SubscriptionStatusResponse)
async def subscription_status(
    ctx: Annotated[TenantContext, Depends(get_tenant)],
) -> SubscriptionStatusResponse:
    return SubscriptionStatusResponse(
        tier=ctx.tenant.tier,
        status=ctx.tenant.subscription_status,
        period_end=ctx.tenant.subscription_current_period_end,
        cancel_at_period_end=ctx.tenant.subscription_status == "canceling",
    )


@router.post("/stripe/webhook/subscription", include_in_schema=False)
async def subscription_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
) -> dict[str, bool]:
    payload = await request.body()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid webhook") from exc

    event_type = str(event.get("type", ""))
    handler = WEBHOOK_HANDLERS.get(event_type)
    if handler is None:
        return {"received": True}

    try:
        await handler(event["data"]["object"], db)
    except Exception:
        logger.exception("stripe_subscription_webhook_failed", extra={"event_type": event_type, "event_id": event.get("id")})
        raise
    return {"received": True}
