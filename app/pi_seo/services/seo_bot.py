"""SEO Bot service using Pi AI Cloud routing."""

from app.core.exceptions import AIProviderError
from app.core.logging_conf import get_logger
from app.pi_ai_cloud.services.completion import CompletionService
from app.pi_seo.prompts import build_seo_bot_prompt, parse_seo_bot_output
from app.pi_seo.schemas import SeoBotGenerateRequest, SeoBotVariant
from app.shared.license.models import License

logger = get_logger(__name__)


class SeoBotService:
    def __init__(self, completion: CompletionService) -> None:
        self.completion = completion

    async def generate(self, lic: License, req: SeoBotGenerateRequest) -> tuple[list[SeoBotVariant], dict]:
        system, user = build_seo_bot_prompt(req)

        result = await self.completion.complete(
            lic,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1500 if req.variants > 1 else 600,
            temperature=0.7,
            quality="balanced",
            source_plugin="pi-seo",
            source_endpoint="seo_bot.generate",
        )

        try:
            variants = parse_seo_bot_output(result.text, expected=req.variants)
        except ValueError as e:
            logger.error("seo_bot_parse_error", extra={"raw": result.text[:500]})
            raise AIProviderError(f"Failed to parse AI output: {e}") from e

        return variants, {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "pi_tokens_charged": result.pi_tokens_charged,
            "tokens_used_period": result.tokens_used_period,
            "tokens_limit_period": result.tokens_limit_period,
            "model": "pi-ai-cloud",
        }
