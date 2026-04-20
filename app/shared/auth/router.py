"""/v1/auth/* endpoints — dashboard login/signup + JWT issuance."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from typing import Annotated

from sqlalchemy import func, select

from app.core.deps import DbSession
from app.core.exceptions import PiException
from app.pi_ai_cloud.models import TokenWallet
from app.shared.auth.schemas import (
    LoginRequest,
    MeResponse,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
from app.shared.auth.service import AuthService
from app.shared.license.models import License

router = APIRouter()


def _public(user) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        is_admin=user.is_admin,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )


@router.post("/signup", response_model=TokenResponse)
async def signup(req: SignupRequest, db: DbSession) -> TokenResponse:
    svc = AuthService(db)
    user = await svc.create_user(email=req.email, password=req.password, name=req.name)
    token, expires_in = AuthService.create_token(user)
    return TokenResponse(token=token, expires_in=expires_in, user=_public(user))


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: DbSession) -> TokenResponse:
    svc = AuthService(db)
    user = await svc.authenticate(req.email, req.password)
    token, expires_in = AuthService.create_token(user)
    return TokenResponse(token=token, expires_in=expires_in, user=_public(user))


@router.get("/me", response_model=MeResponse)
async def me(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> MeResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer JWT",
        )
    jwt_token = authorization.split(" ", 1)[1].strip()
    payload = AuthService.decode_token(jwt_token)
    if payload.get("type") != "user":
        raise PiException(401, "not_a_user_token", "Dùng license key ở endpoint plugin.")

    user_id = int(payload.get("sub", 0))
    svc = AuthService(db)
    user = await svc.get_by_id(user_id)
    if user is None or not user.is_active:
        raise PiException(401, "user_not_found", "Tài khoản không tồn tại.")

    # Owned licenses (by email match — later swap to user_id FK)
    lic_count_q = select(func.count(License.id)).where(License.email == user.email)
    license_count = int((await db.execute(lic_count_q)).scalar_one())

    # Aggregated wallet balance across all licenses owned
    balance_q = (
        select(func.coalesce(func.sum(TokenWallet.balance), 0))
        .join(License, License.id == TokenWallet.license_id)
        .where(License.email == user.email)
    )
    total_balance = int((await db.execute(balance_q)).scalar_one())

    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_admin=user.is_admin,
        is_verified=user.is_verified,
        created_at=user.created_at,
        license_count=license_count,
        token_balance=total_balance,
    )


@router.post("/logout")
async def logout() -> dict[str, bool]:
    """Client-side logout is sufficient (discard JWT); this endpoint exists
    purely for UX (future: blacklist token if we add one)."""
    return {"success": True}
