from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.billing import stripe_subscription as sub
from app.billing.router import WEBHOOK_HANDLERS
from app.billing.stripe_subscription import StripeSubscriptionService
from app.saas.models import Tenant, Token


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDb:
    def __init__(self, tenant=None, token=None):
        self.tenant = tenant
        self.token = token

    async def get(self, model, ident):
        if model is Tenant and self.tenant and self.tenant.id == ident:
            return self.tenant
        return None

    async def execute(self, stmt):  # noqa: ARG002
        statement = str(stmt)
        if "tokens" in statement:
            return FakeResult(self.token)
        return FakeResult(self.tenant)


def tenant(**kwargs):
    data = {
        "id": 7,
        "license_key": "TESTING-12345-DEMO0-KEYAA",
        "domain": "example.com",
        "tier": "free",
        "status": "active",
        "features": [],
    }
    data.update(kwargs)
    return Tenant(**data)


def token():
    return Token(tenant_id=7, balance=0, monthly_quota=0, used_this_month=12)


@pytest.mark.asyncio
async def test_create_checkout_uses_subscription_mode(monkeypatch):
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    create = Mock(return_value={"url": "https://checkout.test/session"})
    monkeypatch.setattr(sub.stripe.checkout.Session, "create", create)

    url = await StripeSubscriptionService.create_checkout(
        tenant(),
        "pro",
        "https://ok.test",
        "https://cancel.test",
    )

    assert url == "https://checkout.test/session"
    assert create.call_args.kwargs["mode"] == "subscription"
    assert create.call_args.kwargs["line_items"] == [{"price": "price_pro", "quantity": 1}]


@pytest.mark.asyncio
async def test_subscription_created_sets_tier_and_quota(monkeypatch):
    monkeypatch.setenv("STRIPE_MAX_PRICE_ID", "price_max")
    t = tenant()
    tok = token()
    db = FakeDb(t, tok)
    stripe_sub = {
        "id": "sub_123",
        "status": "active",
        "metadata": {"tenant_id": "7", "target_tier": "max"},
        "current_period_end": 1_800_000_000,
        "items": {"data": [{"price": {"id": "price_max"}}]},
    }

    await sub.handle_subscription_created(stripe_sub, db)

    assert t.tier == "max"
    assert t.stripe_subscription_id == "sub_123"
    assert t.subscription_status == "active"
    assert tok.monthly_quota == 500_000
    assert tok.used_this_month == 0


@pytest.mark.asyncio
async def test_subscription_updated_changes_tier_from_price(monkeypatch):
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    t = tenant(tier="max", stripe_subscription_id="sub_123")
    tok = token()
    db = FakeDb(t, tok)

    await sub.handle_subscription_updated(
        {
            "id": "sub_123",
            "status": "active",
            "current_period_end": 1_800_000_000,
            "items": {"data": [{"price": {"id": "price_pro"}}]},
        },
        db,
    )

    assert t.tier == "pro"
    assert tok.monthly_quota == 100_000


@pytest.mark.asyncio
async def test_subscription_deleted_downgrades_to_free():
    t = tenant(tier="max", stripe_subscription_id="sub_123")
    tok = token()
    db = FakeDb(t, tok)

    await sub.handle_subscription_deleted({"id": "sub_123"}, db)

    assert t.tier == "free"
    assert t.subscription_status == "canceled"
    assert t.stripe_subscription_id is None
    assert tok.monthly_quota == 5_000


@pytest.mark.asyncio
async def test_invoice_paid_resets_usage():
    t = tenant(tier="pro", stripe_subscription_id="sub_123")
    tok = token()
    db = FakeDb(t, tok)

    await sub.handle_invoice_paid({"subscription": "sub_123", "period_end": 1_800_000_000}, db)

    assert t.subscription_status == "active"
    assert tok.used_this_month == 0
    assert tok.reset_at == datetime.fromtimestamp(1_800_000_000, tz=timezone.utc)


@pytest.mark.asyncio
async def test_invoice_failed_marks_past_due():
    t = tenant(tier="pro", stripe_subscription_id="sub_123")
    db = FakeDb(t)

    await sub.handle_invoice_failed({"subscription": "sub_123"}, db)

    assert t.subscription_status == "past_due"


@pytest.mark.asyncio
async def test_handlers_are_idempotent_for_same_subscription_created():
    t = tenant()
    tok = token()
    db = FakeDb(t, tok)
    event_obj = {
        "id": "sub_123",
        "status": "active",
        "metadata": {"tenant_id": "7", "target_tier": "pro"},
        "current_period_end": 1_800_000_000,
        "items": {"data": [{"price": {"id": "price_pro"}}]},
    }

    await sub.handle_subscription_created(event_obj, db)
    await sub.handle_subscription_created(event_obj, db)

    assert t.tier == "pro"
    assert t.stripe_subscription_id == "sub_123"
    assert tok.used_this_month == 0


def test_webhook_event_coverage():
    assert set(WEBHOOK_HANDLERS) == {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }


@pytest.mark.asyncio
async def test_change_tier_modifies_stripe_subscription(monkeypatch):
    monkeypatch.setenv("STRIPE_MAX_PRICE_ID", "price_max")
    retrieve = Mock(return_value={"items": {"data": [{"id": "si_123"}]}})
    modify = Mock()
    monkeypatch.setattr(sub.stripe.Subscription, "retrieve", retrieve)
    monkeypatch.setattr(sub.stripe.Subscription, "modify", modify)
    t = tenant(tier="pro", stripe_subscription_id="sub_123")
    db = FakeDb(t, token())

    await StripeSubscriptionService.upgrade_or_downgrade(t, "max", db)

    assert t.tier == "max"
    modify.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_sets_canceling(monkeypatch):
    modify = Mock()
    monkeypatch.setattr(sub.stripe.Subscription, "modify", modify)
    t = tenant(tier="pro", stripe_subscription_id="sub_123")
    db = FakeDb(t, token())

    await StripeSubscriptionService.cancel(t, db)

    assert t.subscription_status == "canceling"
    modify.assert_called_once_with("sub_123", cancel_at_period_end=True)
