"""Health + readiness endpoints for monitoring."""

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.db import get_db
from app.core.redis_client import get_redis

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — always returns ok if the process is up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    db=Depends(get_db),
    redis=Depends(get_redis),
) -> dict[str, object]:
    """Readiness probe — checks DB + Redis."""
    checks: dict[str, object] = {"status": "ok"}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {e!s}"
        checks["status"] = "degraded"

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {e!s}"
        checks["status"] = "degraded"

    return checks
