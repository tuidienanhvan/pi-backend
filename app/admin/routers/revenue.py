"""GET /v1/admin/revenue — revenue + margin breakdown."""

from fastapi import APIRouter, Query

from app.admin.schemas import AdminRevenueResponse
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


@router.get("/revenue", response_model=AdminRevenueResponse)
async def revenue(
    admin: CurrentAdmin,
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
) -> AdminRevenueResponse:  # noqa: ARG001
    data = await AdminService(db).revenue(days)
    return AdminRevenueResponse(**data)
