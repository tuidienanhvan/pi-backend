"""POST /v1/ai/complete — primary paid endpoint.

This is the ONLY endpoint all Pi plugins should call for AI work.
Each call deducts from the customer's token wallet.
"""

from fastapi import APIRouter

from app.core.deps import DbSession, CurrentLicense
from app.core.exceptions import PiException
from app.pi_ai_cloud.schemas import CompleteRequest, CompleteResponse
from app.pi_ai_cloud.services.completion import CompletionService

router = APIRouter()


@router.post("/complete", response_model=CompleteResponse)
async def complete(
    req: CompleteRequest,
    lic: CurrentLicense,
    db: DbSession,
) -> CompleteResponse:
    svc = CompletionService(db)
    result = await svc.complete(
        lic,
        messages=[m.model_dump() for m in req.messages],
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        quality=req.quality,
        source_plugin=req.source_plugin,
        source_endpoint=req.source_endpoint,
    )
    # PiException subclasses (QuotaExceeded, NoKeysAvailable) auto-convert to HTTP by middleware

    return CompleteResponse(
        success=True,
        text=result.text,
        pi_tokens_charged=result.pi_tokens_charged,
        tokens_used_period=result.tokens_used_period,
        tokens_limit_period=result.tokens_limit_period,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
