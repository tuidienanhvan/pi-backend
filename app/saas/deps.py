"""Tenant and admin dependencies for SaaS endpoints."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.saas.jwt import decode_tenant_token
from app.saas.models import Tenant
from app.shared.auth.deps import CurrentAdmin
from app.shared.auth.models import User


@dataclass(frozen=True)
class TenantContext:
    tenant: Tenant
    claims: dict

    @property
    def tenant_id(self) -> int:
        return self.tenant.id

    @property
    def features(self) -> list[str]:
        return list(self.tenant.features or [])


async def get_tenant(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_pi_site: Annotated[str | None, Header()] = None,
) -> TenantContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing Bearer tenant JWT",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    claims = decode_tenant_token(token)
    tenant_id = int(claims.get("tenant_id") or claims.get("sub") or 0)
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant inactive or not found")

    if x_pi_site and x_pi_site.lower().strip() != tenant.domain:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant domain mismatch")

    if claims.get("domain") and claims["domain"] != tenant.domain:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token domain mismatch")

    return TenantContext(tenant=tenant, claims=claims)


def require_feature(feature: str):
    async def dependency(ctx: Annotated[TenantContext, Depends(get_tenant)]) -> TenantContext:
        if feature not in ctx.features:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Feature not enabled: {feature}")
        return ctx

    return dependency


async def get_admin_user(admin: CurrentAdmin) -> User:
    return admin


async def resolve_tenant_by_license(
    db: AsyncSession,
    *,
    license_key: str,
    domain: str,
) -> Tenant | None:
    q = select(Tenant).where(Tenant.license_key == license_key, Tenant.domain == domain)
    return (await db.execute(q)).scalar_one_or_none()

