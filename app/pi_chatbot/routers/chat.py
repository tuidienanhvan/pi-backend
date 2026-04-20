"""Pi Chatbot — chat reply + RAG endpoints."""

import time

from fastapi import APIRouter

from app.core.deps import DbSession, RateLimitedLicense
from app.pi_chatbot.schemas import (
    ChatbotReplyRequest,
    ChatbotReplyResponse,
    RagChunk,
    RagQueryRequest,
    RagQueryResponse,
)
from app.pi_ai_cloud.services.completion import CompletionService
from app.pi_ai_cloud.services.wallet import InsufficientTokens
from app.shared.license.service import LicenseService
from app.core.exceptions import PiException

router = APIRouter()


@router.post("/reply", response_model=ChatbotReplyResponse)
async def reply(
    req: ChatbotReplyRequest,
    lic: RateLimitedLicense,
    db: DbSession,
) -> ChatbotReplyResponse:
    """Generate a chatbot reply via Pi AI Cloud. Consumes tokens."""
    started = time.perf_counter()
    svc = CompletionService(db)

    system = req.system_prompt or (
        "Bạn là chatbot hỗ trợ website. Trả lời ngắn gọn, lịch sự, bằng tiếng Việt "
        "(trừ khi user nói tiếng Anh). Nếu không biết rõ, gợi ý khách liên hệ team human."
    )
    if req.rag_context:
        system += "\n\nThông tin tham khảo:\n" + req.rag_context

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": req.message},
    ]
    try:
        result = await svc.complete(
            lic,
            messages=messages,
            max_tokens=400,
            temperature=0.6,
            quality="balanced",
            source_plugin="pi-chatbot-pro",
            source_endpoint="chatbot.reply",
        )
    except InsufficientTokens as e:
        raise PiException(
            402,
            "insufficient_tokens",
            f"Need {e.requested} tokens, wallet has {e.balance}. Top up via Pi AI Cloud.",
        ) from e

    # Log to shared usage
    svc_lic = LicenseService(db)
    await svc_lic.log_usage(
        lic,
        "chatbot.reply",
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

    return ChatbotReplyResponse(
        success=True,
        reply=result.text,
        tokens_charged=result.pi_tokens_charged,
        provider_used=result.provider_slug,
    )


@router.post("/rag/query", response_model=RagQueryResponse)
async def rag_query(
    req: RagQueryRequest,
    lic: RateLimitedLicense,
    db: DbSession,  # noqa: ARG001
) -> RagQueryResponse:
    """Query the knowledge base for relevant chunks. PLACEHOLDER — Phase 3."""
    # TODO: real impl — pgvector or Qdrant. For now, returns empty.
    return RagQueryResponse(success=True, chunks=[])


@router.post("/kb/upload")
async def kb_upload(lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    """Placeholder — multipart upload needs different signature."""
    return {"success": False, "message": "Upload endpoint TBD in Phase 3"}


@router.get("/kb/list")
async def kb_list(lic: RateLimitedLicense, db: DbSession) -> dict:  # noqa: ARG001
    """Placeholder KB doc listing."""
    return {"success": True, "docs": []}


@router.get("/status")
async def status(lic: RateLimitedLicense) -> dict:
    return {
        "plugin": "pi-chatbot",
        "tier": lic.tier,
        "endpoints": ["reply", "rag/query", "kb/upload", "kb/list"],
    }
