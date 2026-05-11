"""JWT helpers for short-lived tenant iframe sessions."""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import PiException


def create_tenant_token(
    *,
    tenant_id: int,
    domain: str,
    tier: str,
    features: list[str],
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    expires_in = int((expires_minutes or settings.tenant_jwt_expire_minutes) * 60)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(tenant_id),
        "type": "tenant",
        "tenant_id": tenant_id,
        "domain": domain,
        "tier": tier,
        "features": features,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_tenant_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise PiException(401, "invalid_tenant_token", "Tenant JWT invalid or expired.") from exc

    if payload.get("type") != "tenant":
        raise PiException(401, "invalid_token_type", "Expected tenant JWT.")
    return payload

