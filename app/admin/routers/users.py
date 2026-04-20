"""GET /v1/admin/users — list dashboard accounts."""

from fastapi import APIRouter, Query

from app.admin.schemas import AdminUsersResponse
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    admin: CurrentAdmin,
    db: DbSession,
    q: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminUsersResponse:  # noqa: ARG001
    items, total = await AdminService(db).list_users(q, limit, offset)
    return AdminUsersResponse(items=items, total=total)
