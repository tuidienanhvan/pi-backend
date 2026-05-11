"""/v1/auth/* endpoints — dashboard login/signup + JWT issuance."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from typing import Annotated

from sqlalchemy import func, select

from app.core.deps import DbSession
from app.core.exceptions import PiException
from app.pi_ai_cloud.models import TokenWallet
from app.shared.schemas.responses import BaseResponse
from app.shared.auth.schemas import (
    LoginRequest,
    MeResponse,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
from app.shared.auth.service import AuthService
from app.shared.license.models import License, Site
from app.shared.license.schemas import LicenseRegisterCredentialsRequest
from app.shared.license.service import LicenseService

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


@router.post("/signup", response_model=BaseResponse[TokenResponse])
async def signup(req: SignupRequest, db: DbSession) -> BaseResponse[TokenResponse]:
    svc = AuthService(db)
    user = await svc.create_user(email=req.email, password=req.password, name=req.name)
    token, expires_in = await svc.create_token(user)
    data = TokenResponse(token=token, expires_in=expires_in, user=_public(user))
    return BaseResponse(data=data, message="Đăng ký thành công.")


@router.post("/login", response_model=BaseResponse[TokenResponse])
async def login(req: LoginRequest, db: DbSession) -> BaseResponse[TokenResponse]:
    svc = AuthService(db)
    user = await svc.authenticate(req.email, req.password)
    token, expires_in = await svc.create_token(user)
    data = TokenResponse(token=token, expires_in=expires_in, user=_public(user))
    return BaseResponse(data=data, message="Đăng nhập thành công.")


@router.get("/me", response_model=BaseResponse[MeResponse])
async def me(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> BaseResponse[MeResponse]:
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
    
    # Highest tier owned
    tier_q = select(License.tier).where(License.email == user.email)
    tiers = (await db.execute(tier_q)).scalars().all()
    highest_tier = "free"
    if "max" in tiers: highest_tier = "max"
    elif "pro" in tiers: highest_tier = "pro"

    data = MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_admin=user.is_admin,
        is_verified=user.is_verified,
        created_at=user.created_at,
        license_count=license_count,
        token_balance=total_balance,
        tier=highest_tier,
    )
    return BaseResponse(data=data)


@router.post("/logout")
async def logout() -> dict[str, bool]:
    """Client-side logout is sufficient (discard JWT); this endpoint exists
    purely for UX (future: blacklist token if we add one)."""
    return {"success": True}


@router.post("/register-credentials")
async def register_credentials(
    req: LicenseRegisterCredentialsRequest, db: DbSession
) -> dict[str, bool]:
    """Plugin calls this to auto-save Application Password on backend."""
    svc = LicenseService(db)
    ok = await svc.register_credentials(
        email=req.email, domain=req.domain, app_pass=req.app_pass
    )
    if not ok:
        # Site might not be activated yet, that's fine, we can't save it yet
        # or the email doesn't match the license owner.
        return {"success": False}
    await db.commit()
    return {"success": True}


@router.get("/sites/credentials")
async def get_site_credentials(
    domain: str,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Dashboard calls this with its current domain to get the auto-generated App Pass."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing JWT")
    
    jwt_token = authorization.split(" ", 1)[1].strip()
    payload = AuthService.decode_token(jwt_token)
    user_id = int(payload.get("sub", 0))
    
    auth_svc = AuthService(db)
    user = await auth_svc.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    lic_svc = LicenseService(db)
    domain = lic_svc._normalise_domain(domain)

    # Find site belonging to any license owned by this user
    q = (
        select(Site)
        .join(License, License.id == Site.license_id)
        .where(License.email == user.email, Site.domain == domain)
    )
    result = await db.execute(q)
    site = result.scalar_one_or_none()

    if not site or not site.app_pass:
        raise HTTPException(status_code=404, detail="Site credentials not found")

    return {
        "success": True,
        "username": "admin", # Defaulting to admin, we could sync this too later
        "app_pass": site.app_pass,
        "site_url": f"https://{domain}" # basic fallback
    }
