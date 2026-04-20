"""Anthropic Claude wrapper — async, with retry + error mapping."""

from typing import Any

from anthropic import AsyncAnthropic, APIConnectionError, APIStatusError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import AIProviderError
from app.core.logging_conf import get_logger

logger = get_logger(__name__)


class ClaudeService:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            logger.warning("anthropic_api_key_missing — Claude calls will fail")
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
    )
    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        response_format: str = "text",
    ) -> dict[str, Any]:
        """Call Claude and return dict with text + usage stats.

        Returns: { text, input_tokens, output_tokens, model, stop_reason }
        Raises AIProviderError on unrecoverable failures.
        """
        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except APIStatusError as e:
            logger.error("claude_api_status_error", extra={"status": e.status_code, "msg": str(e)})
            raise AIProviderError(f"Anthropic API error: HTTP {e.status_code}") from e
        except APIConnectionError as e:
            raise AIProviderError("Anthropic API unreachable") from e

        text = ""
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "")

        return {
            "text": text.strip(),
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": resp.model,
            "stop_reason": resp.stop_reason,
        }
