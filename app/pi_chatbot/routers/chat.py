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
            source_plugin="pi-chatbot",
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
        provider_used="pi-ai-cloud",
    )


@router.post("/rag/query", response_model=RagQueryResponse)
async def rag_query(
    req: RagQueryRequest,  # noqa: ARG001
    lic: RateLimitedLicense,  # noqa: ARG001
    db: DbSession,  # noqa: ARG001
) -> RagQueryResponse:
    """Query the knowledge base for relevant chunks. PHASE 3 — not yet wired.

    Requires pgvector or Qdrant infrastructure. Returns 501 so plugin
    callers can detect unwired state instead of receiving silent empty success.
    """
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail="RAG query not implemented — Phase 3 (pgvector/Qdrant pending)",
    )


@router.post("/kb/upload")
async def kb_upload(lic: RateLimitedLicense) -> dict:  # noqa: ARG001
    """KB document upload — PHASE 3 not yet wired."""
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail="KB upload not implemented — Phase 3 (file storage + embedding pipeline pending)",
    )


@router.get("/kb/list")
async def kb_list(lic: RateLimitedLicense, db: DbSession) -> dict:  # noqa: ARG001
    """KB document listing — PHASE 3 not yet wired."""
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail="KB list not implemented — Phase 3 (kb_documents table pending)",
    )


@router.get("/status")
async def status(lic: RateLimitedLicense) -> dict:
    return {
        "plugin": "pi-chatbot",
        "tier": lic.tier,
        "endpoints": ["reply", "rag/query", "kb/upload", "kb/list"],
    }
