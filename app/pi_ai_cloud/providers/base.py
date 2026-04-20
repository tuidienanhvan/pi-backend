"""Provider adapter interface — each AI backend implements this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    upstream_cost_cents: int = 0


class ProviderAdapter(ABC):
    """Base interface — all provider adapters return the same shape."""

    slug: str
    adapter_type: str  # 'openai_compat' | 'anthropic' | 'gemini'

    @abstractmethod
    async def complete(
        self,
        *,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        temperature: float,
        api_key: str,
        base_url: str,
    ) -> CompletionResult:
        """Call the upstream AI and return normalised result.

        Raises on any failure (4xx/5xx/timeout) — router catches + fallbacks.
        """
        raise NotImplementedError
