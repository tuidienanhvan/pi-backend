"""Provider router — picks which upstream AI to call.

Strategy:
  1. Filter by quality tier (fast = free providers only, best = paid too)
  2. Filter healthy providers
  3. Sort by priority (lower first) + tier (free first within same priority)
  4. Try each in order; on failure, mark unhealthy + try next
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_conf import get_logger
from app.pi_ai_cloud.models import AiProvider

logger = get_logger(__name__)


class NoProviderAvailable(Exception):
    pass


class ProviderRouter:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def pick_candidates(self, quality: str = "balanced") -> list[AiProvider]:
        """Return ordered list of providers to try, best-first."""
        q = select(AiProvider).where(
            AiProvider.is_enabled.is_(True),
            AiProvider.health_status != "down",
        )

        # Quality gating
        if quality == "fast":
            q = q.where(AiProvider.tier == "free")
        elif quality == "best":
            # All allowed — free first still, but paid fallback open
            pass
        else:  # balanced
            pass

        q = q.order_by(AiProvider.priority.asc(), AiProvider.tier.asc())
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def mark_success(self, provider: AiProvider) -> None:
        from datetime import datetime, timezone

        provider.health_status = "healthy"
        provider.consecutive_failures = 0
        provider.last_success_at = datetime.now(timezone.utc)
        provider.last_error = ""
        await self.db.flush()

    async def mark_failure(self, provider: AiProvider, error: str) -> None:
        from datetime import datetime, timezone

        provider.consecutive_failures += 1
        provider.last_failure_at = datetime.now(timezone.utc)
        provider.last_error = error[:500]

        # Circuit breaker
        if provider.consecutive_failures >= 5:
            provider.health_status = "down"
            logger.warning(
                "provider_circuit_open",
                extra={"slug": provider.slug, "failures": provider.consecutive_failures},
            )
        elif provider.consecutive_failures >= 2:
            provider.health_status = "degraded"
        await self.db.flush()
