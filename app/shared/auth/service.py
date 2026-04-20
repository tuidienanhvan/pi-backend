"""Auth service — password hashing (bcrypt) + JWT sign/verify.

NOTE: We use `bcrypt` directly instead of passlib because passlib (last
release 2020) is incompatible with bcrypt 4.x — its init-time backend
detection calls hashpw with a long probe string, which bcrypt 4.x rejects
as > 72 bytes. Using bcrypt directly gives us simpler code + no init bug.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import PiException
from app.shared.auth.models import User


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Password helpers (bcrypt direct) ─────────────────
    @staticmethod
    def hash_password(raw: str) -> str:
        # bcrypt only supports passwords up to 72 bytes; truncate to be safe
        raw_b = raw.encode("utf-8")[:72]
        hashed = bcrypt.hashpw(raw_b, bcrypt.gensalt(rounds=12))
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(raw: str, hashed: str) -> bool:
        try:
            raw_b = raw.encode("utf-8")[:72]
            return bcrypt.checkpw(raw_b, hashed.encode("utf-8"))
        except ValueError:
            return False

    # ─── JWT helpers ────────────────────────────────────
    @staticmethod
    def create_token(user: User) -> tuple[str, int]:
        """Return (jwt_string, expires_in_seconds)."""
        expires_in = settings.jwt_expire_minutes * 60
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "is_admin": user.is_admin,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
            "type": "user",  # distinguishes from license Bearer
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return token, expires_in

    @staticmethod
    def decode_token(token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError as e:
            raise PiException(401, "invalid_token", f"JWT decode failed: {e}") from e

    # ─── User CRUD ──────────────────────────────────────
    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        q = select(User).where(User.email == email.lower().strip())
        return (await self.db.execute(q)).scalar_one_or_none()

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        name: str = "",
        is_admin: bool = False,
    ) -> User:
        if await self.get_by_email(email):
            raise PiException(409, "email_in_use", "Email đã được sử dụng.")
        user = User(
            email=email.lower().strip(),
            name=name.strip(),
            password_hash=self.hash_password(password),
            is_admin=is_admin,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.get_by_email(email)
        if user is None or not user.is_active:
            raise PiException(401, "invalid_credentials", "Sai email hoặc mật khẩu.")
        if not self.verify_password(password, user.password_hash):
            raise PiException(401, "invalid_credentials", "Sai email hoặc mật khẩu.")
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()
        return user
