"""FastAPI dependencies — auth, license, rate limit."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.shared.license.models import License
from app.core.redis_client import get_redis
from app.shared.license.service import LicenseService
from app.shared.rate_limit import RateLimiter

DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]


async def _resolve_license(
    db: AsyncSession,
    authorization: str | None,
) -> License:
    """Shared: parse Bearer + load License row. Does NOT check site."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key = authorization.split(" ", 1)[1].strip()
    if not key.startswith(settings.license_key_prefix):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid license key format")

    svc = LicenseService(db)
    lic = await svc.get_by_key(key)
    if lic is None or not lic.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "License invalid or revoked")
    return lic


async def get_license(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_pi_site: Annotated[str | None, Header()] = None,
) -> License:
    """Parse `Authorization: Bearer <license_key>` → load License row + validate site.

    Validates `X-Pi-Site` header (must match an activated site). Used for plugin
    endpoints that require the site to have been activated (feature calls, stats).
    For the /activate endpoint itself use `get_license_for_activate` instead.
    """
    lic = await _resolve_license(db, authorization)
    if x_pi_site and not await LicenseService(db).site_is_activated(lic, x_pi_site):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Site {x_pi_site} not activated for this license",
        )
    return lic


async def get_license_for_activate(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> License:
    """License auth WITHOUT site-activated check — for /activate + /verify
    endpoints where the site is being registered right now."""
    return await _resolve_license(db, authorization)


async def enforce_rate_limit(
    redis: RedisClient,
    lic: Annotated[License, Depends(get_license)],
) -> License:
    """Check both burst (per-minute) + monthly quota. Raises 429 if exceeded."""
    limiter = RateLimiter(redis)
    await limiter.check_burst(lic.key, settings.rate_limit_burst_per_minute)
    quota = settings.monthly_quota_for.get(lic.tier, settings.rate_limit_free_per_month)
    await limiter.check_monthly(lic.key, quota)
    return lic


CurrentLicense = Annotated[License, Depends(get_license)]
LicenseForActivate = Annotated[License, Depends(get_license_for_activate)]
RateLimitedLicense = Annotated[License, Depends(enforce_rate_limit)]
