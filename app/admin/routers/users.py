"""GET /v1/admin/users — list dashboard accounts."""

from fastapi import APIRouter, Query

from app.admin.schemas import AdminUsersResponse, AdminUserItem, AdminUserProfilePatch
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


@router.get("/users/{user_id}", response_model=AdminUserItem)
async def get_user_detail(
    admin: CurrentAdmin,
    db: DbSession,
    user_id: int,
) -> AdminUserItem:  # noqa: ARG001
    item = await AdminService(db).get_user_detail(user_id)
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return item


@router.patch("/users/{user_id}/profile", response_model=AdminUserItem)
async def patch_user_profile(
    admin: CurrentAdmin,
    db: DbSession,
    user_id: int,
    payload: AdminUserProfilePatch,
) -> AdminUserItem:  # noqa: ARG001
    item = await AdminService(db).patch_user_profile(user_id, payload)
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return item