"""Stripe Subscription orchestrator for Pi tenant tier upgrades."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_conf import get_logger
from app.saas.models import Tenant, Token
from app.shared.license.models import License
from app.pi_ai_cloud.models import TokenWallet, LicensePackage
from app.saas.tiers import TIER_TOKEN_QUOTA
from app.shared.email import send_email

logger = get_logger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

SubscribableTier = Literal["pro", "max"]


def _price_ids() -> dict[str, str]:
    return {
        "pro": os.getenv("STRIPE_PRO_PRICE_ID", ""),
        "max": os.getenv("STRIPE_MAX_PRICE_ID", ""),
    }


def price_id_for_tier(tier: str) -> str:
    price_id = _price_ids().get(tier, "")
    if not price_id:
        raise ValueError(f"Stripe price ID missing for tier: {tier}")
    return price_id


def tier_for_price_id(price_id: str) -> str | None:
    for tier, configured_price_id in _price_ids().items():
        if configured_price_id and configured_price_id == price_id:
            return tier
    return None


def _timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _subscription_price_id(sub: Any) -> str:
    items = _get(_get(sub, "items", {}), "data", []) or []
    if not items:
        return ""
    first = items[0]
    price = _get(first, "price", {})
    return str(_get(price, "id", "") or "")


async def sync_token_quota(db: AsyncSession, tenant: Tenant, *, reset_used: bool = False) -> None:
    result = await db.execute(select(Token).where(Token.tenant_id == tenant.id))
    token = result.scalar_one_or_none()
    if token is None:
        return
    quota = TIER_TOKEN_QUOTA.get(tenant.tier, TIER_TOKEN_QUOTA["free"])
    token.monthly_quota = int(quota or -1)
    if reset_used:
        token.used_this_month = 0
    if tenant.subscription_current_period_end is not None:
        token.reset_at = tenant.subscription_current_period_end


class StripeSubscriptionService:
    @staticmethod
    async def create_checkout(
        tenant: Tenant,
        tier: SubscribableTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout Session in subscription mode."""
        price_id = price_id_for_tier(tier)
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                client_reference_id=str(tenant.id),
                metadata={"tenant_id": str(tenant.id), "target_tier": tier},
                subscription_data={"metadata": {"tenant_id": str(tenant.id), "target_tier": tier}},
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except Exception:
            logger.exception("stripe_subscription_checkout_failed", extra={"tenant_id": tenant.id, "tier": tier})
            raise
        url = _get(session, "url")
        if not url:
            raise RuntimeError("Stripe checkout session did not return a URL")
        return str(url)

    @staticmethod
    async def upgrade_or_downgrade(tenant: Tenant, new_tier: SubscribableTier, db: AsyncSession) -> None:
        """Modify an existing subscription to a new price; webhook remains source of truth."""
        if not tenant.stripe_subscription_id:
            raise ValueError("No active subscription")
        price_id = price_id_for_tier(new_tier)
        try:
            sub = stripe.Subscription.retrieve(tenant.stripe_subscription_id)
            items = _get(_get(sub, "items", {}), "data", []) or []
            item_id = _get(items[0], "id") if items else None
            if not item_id:
                raise RuntimeError("Subscription has no line item")
            stripe.Subscription.modify(
                tenant.stripe_subscription_id,
                items=[{"id": item_id, "price": price_id}],
                proration_behavior="create_prorations",
            )
        except Exception:
            logger.exception("stripe_subscription_change_failed", extra={"tenant_id": tenant.id, "tier": new_tier})
            raise
        tenant.tier = new_tier
        tenant.subscription_status = tenant.subscription_status or "active"
        await sync_token_quota(db, tenant)

    @staticmethod
    async def cancel(tenant: Tenant, db: AsyncSession, at_period_end: bool = True) -> None:
        """Cancel subscription. Defaults to end-of-period."""
        if not tenant.stripe_subscription_id:
            return
        try:
            stripe.Subscription.modify(
                tenant.stripe_subscription_id,
                cancel_at_period_end=at_period_end,
            )
        except Exception:
            logger.exception("stripe_subscription_cancel_failed", extra={"tenant_id": tenant.id})
            raise
        tenant.subscription_status = "canceling"
        await sync_token_quota(db, tenant)


async def handle_checkout_completed(session: Any, db: AsyncSession) -> None:
    sub_id = str(_get(session, "subscription", "") or "")
    tenant_id = int((_get(session, "metadata", {}) or {}).get("tenant_id") or _get(session, "client_reference_id", 0) or 0)
    target_tier = str((_get(session, "metadata", {}) or {}).get("target_tier") or "pro")
    if tenant_id <= 0:
        return
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        return
    tenant.tier = target_tier if target_tier in ("pro", "max") else tenant.tier
    tenant.subscription_status = "active"
    await sync_token_quota(db, tenant, reset_used=True)

    # Sync License table if tenant has a license_key
    if tenant.license_key:
        result = await db.execute(select(License).where(License.key == tenant.license_key))
        lic = result.scalar_one_or_none()
        if lic:
            lic.tier = tenant.tier
            lic.stripe_subscription_id = sub_id or lic.stripe_subscription_id
            
            # Sync TokenWallet (Pi AI Cloud side)
            res_wallet = await db.execute(select(TokenWallet).where(TokenWallet.license_id == lic.id))
            wallet = res_wallet.scalar_one_or_none()
            if wallet:
                # We update the balance too if needed, but balance usually comes from Topups.
                # Here we ensure it matches the SaaS balance if that's the source of truth.
                wallet.balance = tenant.token.balance if hasattr(tenant, 'token') and tenant.token else wallet.balance

            # Sync LicensePackage (Pi AI Cloud side)
            res_pkg = await db.execute(select(LicensePackage).where(LicensePackage.license_id == lic.id))
            pkg = res_pkg.scalar_one_or_none()
            if pkg:
                pkg.package_slug = tenant.tier
                pkg.status = "active"
                pkg.stripe_subscription_id = sub_id or pkg.stripe_subscription_id
            else:
                # Create if missing
                pkg = LicensePackage(
                    license_id=lic.id,
                    package_slug=tenant.tier,
                    status="active",
                    stripe_subscription_id=sub_id or "",
                )
                db.add(pkg)


async def handle_subscription_created(sub: Any, db: AsyncSession) -> None:
    metadata = _get(sub, "metadata", {}) or {}
    tenant_id = int(metadata.get("tenant_id") or 0)
    target_tier = str(metadata.get("target_tier") or tier_for_price_id(_subscription_price_id(sub)) or "pro")
    tenant = await db.get(Tenant, tenant_id) if tenant_id else None
    if tenant is None:
        return
    tenant.tier = target_tier if target_tier in ("pro", "max") else "pro"
    tenant.stripe_subscription_id = str(_get(sub, "id", "") or "")
    tenant.subscription_status = str(_get(sub, "status", "") or "active")
    tenant.subscription_current_period_end = _timestamp(_get(sub, "current_period_end"))
    await sync_token_quota(db, tenant, reset_used=True)
    send_subscription_activated_email(tenant)


async def handle_subscription_updated(sub: Any, db: AsyncSession) -> None:
    sub_id = str(_get(sub, "id", "") or "")
    result = await db.execute(select(Tenant).where(Tenant.stripe_subscription_id == sub_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return
    tier = tier_for_price_id(_subscription_price_id(sub))
    if tier:
        tenant.tier = tier
    tenant.subscription_status = str(_get(sub, "status", "") or tenant.subscription_status or "active")
    tenant.subscription_current_period_end = _timestamp(_get(sub, "current_period_end"))
    await sync_token_quota(db, tenant)


def send_subscription_activated_email(tenant: Tenant) -> bool:
    """Deliver license/dashboard details after Stripe activates a subscription."""
    metadata = tenant.metadata_ or {}
    email = str(metadata.get("email") or metadata.get("user_email") or "")
    user_name = str(metadata.get("name") or metadata.get("user_name") or tenant.name or "Pi user")
    if not email:
        logger.info("subscription_email_skip_no_email", extra={"tenant_id": tenant.id})
        return False

    dashboard_url = os.getenv("PI_DASHBOARD_URL", "https://dashboard.pi-ecosystem.com")
    docs_url = os.getenv("PI_DOCS_INSTALL_URL", "https://docs.pi-ecosystem.com/install")
    return send_email(
        to=email,
        subject=f"Pi {tenant.tier.title()} subscription activated",
        template="subscription_activated",
        context={
            "user_name": user_name,
            "tier": tenant.tier.title(),
            "license_key": tenant.license_key,
            "dashboard_url": f"{dashboard_url}?license={tenant.license_key}",
            "docs_url": docs_url,
        },
    )


async def handle_subscription_deleted(sub: Any, db: AsyncSession) -> None:
    sub_id = str(_get(sub, "id", "") or "")
    result = await db.execute(select(Tenant).where(Tenant.stripe_subscription_id == sub_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return
    tenant.tier = "free"
    tenant.subscription_status = "canceled"
    tenant.stripe_subscription_id = None
    tenant.subscription_current_period_end = None
    await sync_token_quota(db, tenant, reset_used=True)


async def handle_invoice_paid(invoice: Any, db: AsyncSession) -> None:
    sub_id = str(_get(invoice, "subscription", "") or "")
    if not sub_id:
        return
    result = await db.execute(select(Tenant).where(Tenant.stripe_subscription_id == sub_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return
    tenant.subscription_status = "active"
    period_end = _get(invoice, "period_end")
    if period_end:
        tenant.subscription_current_period_end = _timestamp(period_end)
    await sync_token_quota(db, tenant, reset_used=True)


async def handle_invoice_failed(invoice: Any, db: AsyncSession) -> None:
    sub_id = str(_get(invoice, "subscription", "") or "")
    if not sub_id:
        return
    result = await db.execute(select(Tenant).where(Tenant.stripe_subscription_id == sub_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return
    tenant.subscription_status = "past_due"
