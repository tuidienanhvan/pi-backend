"""Admin endpoints for SaaS tenants and token balances."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.saas.deps import get_admin_user
from app.saas.models import AdminAuditLog, Tenant, Token, TokenTransaction
from app.saas.schemas import TenantCreate, TenantItem, TenantPatch, TokenRechargeRequest
from app.saas.tiers import features_for_tier, monthly_quota_for_tier, normalize_tier
from app.shared.auth.models import User

from app.shared.schemas.responses import BaseResponse

router = APIRouter()


def _item(tenant: Tenant) -> TenantItem:
    return TenantItem(
        id=tenant.id,
        domain=tenant.domain,
        site_url=tenant.site_url,
        tier=tenant.tier,
        status=tenant.status,
        features=list(tenant.features or []),
        last_seen_at=tenant.last_seen_at,
    )


async def _audit(
    db: DbSession,
    admin: User,
    action: str,
    tenant: Tenant | None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            actor=admin.email,
            action=action,
            tenant_id=tenant.id if tenant else None,
            metadata_=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
    )

@router.get("/tenants", response_model=BaseResponse[list[TenantItem]])
async def list_tenants(
    db: DbSession,
    admin: User = Depends(get_admin_user),  # noqa: ARG001
    status_filter: str = Query("", alias="status"),
    tier: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> BaseResponse[list[TenantItem]]:
    stmt = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)
    if tier:
        stmt = stmt.where(Tenant.tier == normalize_tier(tier))
    tenants = (await db.execute(stmt)).scalars().all()
    data = [_item(tenant) for tenant in tenants]
    return BaseResponse(data=data, meta={"limit": limit, "offset": offset, "count": len(data)})


@router.post("/tenants", response_model=BaseResponse[TenantItem], status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    db: DbSession,
    admin: User = Depends(get_admin_user),
) -> BaseResponse[TenantItem]:
    q = select(Tenant).where((Tenant.license_key == payload.license_key) | (Tenant.domain == payload.domain))
    if (await db.execute(q)).scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant license or domain already exists")

    tier = normalize_tier(payload.tier)
    tenant = Tenant(
        license_key=payload.license_key,
        domain=payload.domain,
        site_url=payload.site_url,
        tier=tier,
        status=payload.status,
        features=features_for_tier(tier),
    )
    db.add(tenant)
    await db.flush()
    db.add(Token(tenant_id=tenant.id, monthly_quota=monthly_quota_for_tier(tier)))
    await _audit(db, admin, "admin.tenant.create", tenant, {"tier": tier})
    return BaseResponse(data=_item(tenant), message="Tenant created successfully")


@router.patch("/tenants/{tenant_id}", response_model=BaseResponse[TenantItem])
async def update_tenant(
    tenant_id: int,
    payload: TenantPatch,
    db: DbSession,
    admin: User = Depends(get_admin_user),
) -> BaseResponse[TenantItem]:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    before = {"tier": tenant.tier, "status": tenant.status, "features": list(tenant.features or [])}
    if payload.tier is not None:
        tenant.tier = normalize_tier(payload.tier)
        if payload.features is None:
            tenant.features = features_for_tier(tenant.tier)
    if payload.status is not None:
        tenant.status = payload.status
    if payload.features is not None:
        tenant.features = payload.features
    await _audit(db, admin, "admin.tenant.update", tenant, {"before": before})
    return BaseResponse(data=_item(tenant), message="Tenant updated successfully")


@router.post("/tenants/{tenant_id}/tokens/recharge", response_model=BaseResponse[dict])
async def recharge_tokens(
    tenant_id: int,
    payload: TokenRechargeRequest,
    db: DbSession,
    admin: User = Depends(get_admin_user),
) -> BaseResponse[dict]:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    q = select(Token).where(Token.tenant_id == tenant_id)
    wallet = (await db.execute(q)).scalar_one_or_none()
    if wallet is None:
        wallet = Token(tenant_id=tenant_id, monthly_quota=monthly_quota_for_tier(tenant.tier))
        db.add(wallet)
        await db.flush()

    wallet.balance += payload.delta
    tx = TokenTransaction(
        tenant_id=tenant_id,
        delta=payload.delta,
        reason=payload.reason,
        note=payload.note,
    )
    db.add(tx)
    await db.flush()
    await _audit(
        db,
        admin,
        "admin.tokens.recharge",
        tenant,
        {"delta": payload.delta, "reason": payload.reason},
    )
    return BaseResponse(
        data={"balance": wallet.balance, "transaction_id": tx.id},
        message=f"Recharged {payload.delta} tokens"
    )
