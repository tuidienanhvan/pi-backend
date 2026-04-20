"""Auth dependencies — JWT-based user + admin guards."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.db import get_db
from app.core.exceptions import PiException
from app.shared.auth.models import User
from app.shared.auth.service import AuthService
from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Extract user from JWT Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer JWT",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()

    # Reject license keys reaching user endpoints
    if token.startswith("pi_"):
        raise PiException(
            401,
            "wrong_auth_type",
            "License key không phù hợp — cần JWT từ /v1/auth/login.",
        )

    payload = AuthService.decode_token(token)
    if payload.get("type") != "user":
        raise PiException(401, "invalid_token_type", "Invalid token type.")

    svc = AuthService(db)
    user = await svc.get_by_id(int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise PiException(401, "user_not_found", "User not found.")
    return user


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
