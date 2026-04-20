"""Redis-backed rate limiter (sliding window + monthly quota)."""

from datetime import datetime, timezone

from redis.asyncio import Redis

from app.core.exceptions import QuotaExceeded, RateLimitExceeded


class RateLimiter:
    """Two layers:
    - Burst: max N requests per 60 seconds (prevent hammering)
    - Monthly: tracked via UsageLog in DB (checked separately)
    """

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def check_burst(self, key: str, limit_per_minute: int) -> None:
        """Sliding-minute window using Redis INCR + EXPIRE."""
        bucket = f"ratelimit:burst:{key}:{_current_minute()}"
        count = await self.redis.incr(bucket)
        if count == 1:
            await self.redis.expire(bucket, 70)  # grace buffer
        if count > limit_per_minute:
            raise RateLimitExceeded(
                f"Burst limit: max {limit_per_minute} requests/minute"
            )

    async def check_monthly(self, key: str, quota: int) -> None:
        """Monthly quota — stored in Redis as hit counter.

        Source of truth is UsageLog (DB), but we also keep a Redis counter
        for fast pre-check. Reset happens implicitly via TTL.
        """
        bucket = f"ratelimit:monthly:{key}:{_current_month()}"
        count = await self.redis.incr(bucket)
        if count == 1:
            await self.redis.expire(bucket, 60 * 60 * 24 * 35)  # 35 days
        if count > quota:
            raise QuotaExceeded(f"Monthly quota: {quota} requests exhausted")


def _current_minute() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}{now.month:02d}{now.day:02d}{now.hour:02d}{now.minute:02d}"


def _current_month() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}{now.month:02d}"
