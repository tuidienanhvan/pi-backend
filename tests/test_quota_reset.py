from datetime import datetime, timedelta, timezone

import pytest

from app.celery_tasks import token_reset
from app.saas.models import Tenant, Token


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return FakeScalars(self.values)


class FakeSession:
    def __init__(self, tokens, tenants):
        self.tokens = tokens
        self.tenants = tenants
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):  # noqa: ARG002
        return FakeResult(self.tokens)

    async def get(self, model, ident):  # noqa: ARG002
        return self.tenants.get(ident)

    async def commit(self):
        self.committed = True


def tenant(**kwargs):
    data = {
        "id": 1,
        "license_key": "TESTING-12345-DEMO0-KEYAA",
        "domain": "example.com",
        "tier": "free",
        "status": "active",
        "features": [],
    }
    data.update(kwargs)
    return Tenant(**data)


@pytest.mark.asyncio
async def test_reset_due_free_token(monkeypatch):
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    tok = Token(tenant_id=1, monthly_quota=5_000, used_this_month=900, reset_at=now - timedelta(days=1))
    session = FakeSession([tok], {1: tenant()})
    monkeypatch.setattr(token_reset, "AsyncSessionLocal", lambda: session)

    result = await token_reset.reset_due_tokens(now)

    assert result["reset_count"] == 1
    assert tok.used_this_month == 0
    assert tok.monthly_quota == 5_000
    assert tok.reset_at == now + timedelta(days=30)
    assert session.committed is True


@pytest.mark.asyncio
async def test_skip_active_stripe_managed_subscription(monkeypatch):
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    tok = Token(tenant_id=1, monthly_quota=100_000, used_this_month=900, reset_at=now - timedelta(days=1))
    session = FakeSession([tok], {1: tenant(tier="pro", subscription_status="active")})
    monkeypatch.setattr(token_reset, "AsyncSessionLocal", lambda: session)

    result = await token_reset.reset_due_tokens(now)

    assert result["reset_count"] == 0
    assert result["skipped_count"] == 1
    assert tok.used_this_month == 900


@pytest.mark.asyncio
async def test_canceled_subscription_gets_rolling_reset(monkeypatch):
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    tok = Token(tenant_id=1, monthly_quota=100_000, used_this_month=900, reset_at=now - timedelta(days=1))
    session = FakeSession([tok], {1: tenant(tier="pro", subscription_status="canceled")})
    monkeypatch.setattr(token_reset, "AsyncSessionLocal", lambda: session)

    await token_reset.reset_due_tokens(now)

    assert tok.used_this_month == 0
    assert tok.monthly_quota == 100_000
