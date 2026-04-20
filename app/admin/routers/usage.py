"""GET /v1/admin/usage — aggregated usage analytics."""

from fastapi import APIRouter, Query

from app.admin.schemas import AdminUsageResponse
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


@router.get("/usage", response_model=AdminUsageResponse)
async def usage(
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
    plugin: str = Query(""),
    quality: str = Query(""),
    status: str = Query(""),
) -> AdminUsageResponse:
    data = await AdminService(db).usage(
        days=days, plugin=plugin, quality=quality, status=status,
    )
    return AdminUsageResponse(**data)
