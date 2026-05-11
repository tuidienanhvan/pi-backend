from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.saas.deps import TenantContext
from app.saas.middleware import require_feature, require_quota


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDb:
    def __init__(self, token):
        self.token = token

    async def execute(self, stmt):  # noqa: ARG002
        return FakeResult(self.token)


def ctx(tier="free", features=None):
    return TenantContext(
        tenant=SimpleNamespace(id=7, tier=tier, features=features or []),
        claims={"tenant_id": 7},
    )


@pytest.mark.asyncio
async def test_free_tenant_cannot_use_lead_pipeline():
    dependency = require_feature("lead_pipeline")

    with pytest.raises(HTTPException) as exc:
        await dependency(ctx("free"))

    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "feature_not_available"
    assert "Vui lòng nâng cấp" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_pro_tenant_can_use_lead_pipeline():
    dependency = require_feature("lead_pipeline")

    result = await dependency(ctx("pro"))

    assert result.tenant.tier == "pro"


@pytest.mark.asyncio
async def test_enterprise_wildcard_allows_any_feature():
    dependency = require_feature("devops")

    result = await dependency(ctx("enterprise"))

    assert result.tenant.tier == "enterprise"


@pytest.mark.asyncio
async def test_custom_feature_allows_feature_outside_tier_defaults():
    dependency = require_feature("white_label")

    result = await dependency(ctx("free", ["white_label"]))

    assert result.tenant.tier == "free"


@pytest.mark.asyncio
async def test_quota_dependency_blocks_when_exhausted():
    dependency = require_quota(estimated_tokens=200)
    token = SimpleNamespace(monthly_quota=5_000, used_this_month=4_900)

    with pytest.raises(HTTPException) as exc:
        await dependency(ctx("free"), FakeDb(token))

    assert exc.value.status_code == 429
    assert exc.value.detail["error"] == "quota_exceeded"
    assert "Đã hết token tháng này" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_quota_dependency_allows_enterprise_unlimited():
    dependency = require_quota(estimated_tokens=1_000_000)

    result = await dependency(ctx("enterprise"), FakeDb(None))

    assert result.tenant.tier == "enterprise"
