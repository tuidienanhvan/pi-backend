"""Shared async Redis client — used for cache + rate limiting."""

from redis.asyncio import Redis, from_url

from app.core.config import settings

_client: Redis | None = None


async def get_redis() -> Redis:
    """FastAPI dependency — returns the shared Redis client."""
    global _client
    if _client is None:
        _client = from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
