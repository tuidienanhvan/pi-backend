"""Completion orchestrator — quota → pick customer's keys → call → charge.

New per-customer architecture:
  1. QuotaService.check(license_id) — enforce package quota
  2. KeyAllocator.keys_for_license(license_id) — get ONLY this customer's keys
  3. Try each key in health/usage order; on failure mark + try next
  4. Charge Pi tokens against customer's period counter
  5. Log AiUsage with provider_key_id
"""

import os
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AIProviderError, PiException
from app.core.logging_conf import get_logger
from app.pi_ai_cloud.models import AiProvider, AiProviderKey, AiUsage
from app.pi_ai_cloud.providers.base import CompletionResult
from app.pi_ai_cloud.providers.openai_compat import OpenAICompatAdapter
from app.pi_ai_cloud.services.key_allocator import KeyAllocator
from app.pi_ai_cloud.services.quota import QuotaExceeded, QuotaService
from app.shared.license.models import License

logger = get_logger(__name__)

_ADAPTERS = {
    "openai_compat": OpenAICompatAdapter(),
}


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    pi_tokens_charged: int
    tokens_used_period: int
    tokens_limit_period: int
    provider_slug: str


class NoKeysAvailable(PiException):
    def __init__(self) -> None:
        super().__init__(
            status_code=503, code="no_keys_allocated",
            message="No AI provider keys allocated to your account. Contact admin.",
        )


class CompletionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.allocator = KeyAllocator(db)
        self.quota = QuotaService(db)

    async def complete(
        self,
        lic: License,
        *,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        quality: str = "balanced",
        source_plugin: str = "",
        source_endpoint: str = "",
    ) -> Completion:
        # 1. Quota check (raises 402 if exceeded)
        estimated = _estimate_tokens(messages) + max_tokens
        qcheck = await self.quota.check(lic.id, estimated_tokens=estimated, quality=quality)

        # 2. Pick keys belonging to THIS license
        keys = await self.allocator.keys_for_license(lic.id)
        if not keys:
            raise NoKeysAvailable()

        # Filter by quality — map allowed_qualities to provider tiers
        keys = await self._filter_by_quality(keys, quality)
        if not keys:
            raise NoKeysAvailable()

        # 3. Try in order
        last_error: Exception | None = None
        for key in keys:
            provider = await self.db.get(AiProvider, key.provider_id)
            if provider is None or not provider.is_enabled:
                continue

            adapter = _ADAPTERS.get(provider.adapter)
            if adapter is None:
                continue

            api_key = key.key_value.strip()
            if not api_key:
                continue

            started = time.perf_counter()
            try:
                result: CompletionResult = await adapter.complete(
                    messages=messages,
                    model_id=provider.model_id,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    api_key=api_key,
                    base_url=provider.base_url,
                )
                latency = int((time.perf_counter() - started) * 1000)
                await self.allocator.mark_health(key.id, success=True)

                # 4. Compute Pi tokens + charge
                pi_tokens = _compute_pi_tokens(provider, result)
                await self.quota.add_used(lic.id, tokens=pi_tokens)
                await self.allocator.add_tokens_used(key.id, pi_tokens)

                # 5. Log usage
                self.db.add(AiUsage(
                    license_id=lic.id,
                    wallet_id=0,  # legacy; wallet system being phased out
                    provider_id=provider.id,
                    provider_key_id=key.id,
                    source_plugin=source_plugin,
                    source_endpoint=source_endpoint,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    pi_tokens_charged=pi_tokens,
                    upstream_cost_cents=_compute_upstream_cost_cents(provider, result),
                    latency_ms=latency,
                    status="success",
                ))
                await self.db.flush()

                return Completion(
                    text=result.text,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    pi_tokens_charged=pi_tokens,
                    tokens_used_period=qcheck.used + pi_tokens,
                    tokens_limit_period=qcheck.limit,
                    provider_slug=provider.slug,
                )

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await self.allocator.mark_health(key.id, success=False, error=str(exc))
                logger.warning(
                    "provider_key_failed_trying_next",
                    extra={"key_id": key.id, "slug": provider.slug, "error": str(exc)[:200]},
                )
                continue

        raise AIProviderError(
            f"All keys failed. Last error: {last_error!s}" if last_error else "No key returned successfully"
        )

    async def _filter_by_quality(self, keys: list[AiProviderKey], quality: str) -> list[AiProviderKey]:
        """Map quality → provider tier. fast=free only, best=paid allowed, balanced=both."""
        if not keys:
            return keys
        provider_ids = {k.provider_id for k in keys}
        q = select(AiProvider).where(AiProvider.id.in_(provider_ids))
        providers = {p.id: p for p in (await self.db.execute(q)).scalars().all()}

        if quality == "fast":
            allowed_tiers = {"free"}
        elif quality == "best":
            allowed_tiers = {"free", "paid"}  # both, priority order picks cheapest first
        else:  # balanced
            allowed_tiers = {"free", "paid"}

        return [
            k for k in keys
            if k.provider_id in providers and providers[k.provider_id].tier in allowed_tiers
        ]


# ─── Helpers ────────────────────────────────────────────────


def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4


def _compute_pi_tokens(provider: AiProvider, result: CompletionResult) -> int:
    input_cost = result.input_tokens * provider.pi_tokens_per_input
    output_cost = result.output_tokens * provider.pi_tokens_per_output
    return max(1, int(round(input_cost + output_cost)))


def _compute_upstream_cost_cents(provider: AiProvider, result: CompletionResult) -> int:
    in_cost = result.input_tokens * provider.input_cost_per_mtok_cents / 1_000_000
    out_cost = result.output_tokens * provider.output_cost_per_mtok_cents / 1_000_000
    return int(round(in_cost + out_cost))


def _read_provider_key(slug: str) -> str:
    """Legacy: env fallback. New flow uses ai_provider_keys table only."""
    env_name = "PI_AI_KEY_" + slug.upper().replace("-", "_")
    return os.getenv(env_name, "")
