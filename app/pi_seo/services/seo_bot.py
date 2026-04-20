"""SEO Bot service — orchestrates Claude + prompt + parsing."""

import json
import re

from app.core.exceptions import AIProviderError
from app.core.logging_conf import get_logger
from app.pi_seo.prompts import build_seo_bot_prompt, parse_seo_bot_output
from app.pi_seo.schemas import SeoBotGenerateRequest, SeoBotVariant
from app.shared.claude import ClaudeService

logger = get_logger(__name__)


class SeoBotService:
    def __init__(self, claude: ClaudeService | None = None) -> None:
        self.claude = claude or ClaudeService()

    async def generate(self, req: SeoBotGenerateRequest) -> tuple[list[SeoBotVariant], dict]:
        """Return (variants, meta) — meta has token counts for usage logging."""
        system, user = build_seo_bot_prompt(req)

        result = await self.claude.complete(
            system=system,
            user=user,
            max_tokens=1500 if req.variants > 1 else 600,
            temperature=0.7,
        )

        try:
            variants = parse_seo_bot_output(result["text"], expected=req.variants)
        except ValueError as e:
            logger.error("seo_bot_parse_error", extra={"raw": result["text"][:500]})
            raise AIProviderError(f"Failed to parse AI output: {e}") from e

        return variants, {
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "model": result["model"],
        }
