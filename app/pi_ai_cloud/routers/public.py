"""/v1/public/* — endpoints anyone can call (no auth).

Used by marketing pages: /pricing, /catalog, etc.
Returns only customer-visible fields. NEVER exposes keys/providers.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.pi_ai_cloud.models import AiPackage

router = APIRouter()


class PublicPackage(BaseModel):
    slug: str
    display_name: str
    description: str = ""
    price_cents_monthly: int
    price_cents_yearly: int
    token_quota_monthly: int
    allowed_qualities: list[str]
    features: list[str]
    sort_order: int
    is_popular: bool = False  # computed: the "Pro" tier is the recommended default


class PublicPackagesResponse(BaseModel):
    items: list[PublicPackage]


@router.get("/packages", response_model=PublicPackagesResponse)
async def list_public_packages(db: DbSession) -> PublicPackagesResponse:
    q = (
        select(AiPackage)
        .where(AiPackage.is_active.is_(True))
        .order_by(AiPackage.sort_order.asc())
    )
    rows = list((await db.execute(q)).scalars().all())
    # Mark the middle/popular tier — convention: "pro" slug
    items = [
        PublicPackage(
            slug=p.slug,
            display_name=p.display_name,
            description=p.description or "",
            price_cents_monthly=p.price_cents_monthly,
            price_cents_yearly=p.price_cents_yearly,
            token_quota_monthly=p.token_quota_monthly,
            allowed_qualities=list(p.allowed_qualities or []),
            features=list(p.features or []),
            sort_order=p.sort_order,
            is_popular=(p.slug == "pro"),
        )
        for p in rows
    ]
    return PublicPackagesResponse(items=items)
