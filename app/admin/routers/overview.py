"""GET /v1/admin/overview — aggregated system stats."""

from fastapi import APIRouter

from app.admin.schemas import AdminOverviewResponse
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(admin: CurrentAdmin, db: DbSession) -> AdminOverviewResponse:  # noqa: ARG001
    return await AdminService(db).overview()
