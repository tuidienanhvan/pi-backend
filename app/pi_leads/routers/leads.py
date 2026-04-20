"""Pi Leads — scoring + enrichment endpoints."""

import json
import re

from fastapi import APIRouter

from app.core.deps import DbSession, RateLimitedLicense
from app.core.exceptions import PiException
from app.pi_ai_cloud.services.completion import CompletionService
from app.pi_ai_cloud.services.wallet import InsufficientTokens
from app.pi_leads.schemas import (
    LeadEnrichRequest,
    LeadEnrichResponse,
    LeadScoreRequest,
    LeadScoreResponse,
)

router = APIRouter()


@router.post("/score", response_model=LeadScoreResponse)
async def score(
    req: LeadScoreRequest,
    lic: RateLimitedLicense,
    db: DbSession,
) -> LeadScoreResponse:
    """AI-scored lead quality (0-100) + reasoning. Consumes tokens."""
    svc = CompletionService(db)

    prompt = (
        "Bạn là SDR expert. Chấm điểm chất lượng lead (0-100) dựa trên dữ liệu:\n"
        f"Name: {req.lead.name}\n"
        f"Email: {req.lead.email}\n"
        f"Phone: {req.lead.phone}\n"
        f"Message: {req.lead.message[:500]}\n\n"
        "Tiêu chí: business email > personal, có phone > không, message rõ intent > vague. "
        "Trả về JSON: {\"score\": <0-100>, \"reasoning\": \"<1-2 câu lý do>\"}. "
        "KHÔNG có text khác ngoài JSON."
    )

    try:
        result = await svc.complete(
            lic,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
            quality="fast",
            source_plugin="pi-leads-pro",
            source_endpoint="leads.score",
        )
    except InsufficientTokens as e:
        raise PiException(402, "insufficient_tokens", str(e)) from e

    # Parse
    try:
        m = re.search(r"\{.*\}", result.text, re.DOTALL)
        data = json.loads(m.group(0) if m else result.text)
        ai_score = max(0, min(100, int(data.get("score", 50))))
        reasoning = str(data.get("reasoning", ""))[:500]
    except Exception:  # noqa: BLE001
        ai_score = 50
        reasoning = result.text[:200]

    return LeadScoreResponse(success=True, score=ai_score, reasoning=reasoning)


@router.post("/enrich", response_model=LeadEnrichResponse)
async def enrich(
    req: LeadEnrichRequest,
    lic: RateLimitedLicense,
    db: DbSession,  # noqa: ARG001
) -> LeadEnrichResponse:
    """Enrich lead by domain. Placeholder — future: Clearbit/Hunter API proxy."""
    domain = req.domain.lower().strip()
    if not domain or "." not in domain:
        raise PiException(400, "bad_domain", "Invalid domain")

    # Poor man's enrichment: guess industry from TLD + common patterns
    industry = "Unknown"
    if domain.endswith(".edu"):    industry = "Education"
    elif domain.endswith(".gov"):  industry = "Government"
    elif "shop" in domain or "store" in domain: industry = "Retail"
    elif "tech" in domain or "soft" in domain:  industry = "Technology"

    return LeadEnrichResponse(
        success=True,
        company={
            "name": domain.split(".")[0].title(),
            "website": f"https://{domain}",
            "industry": industry,
            "size": "Unknown",
        },
    )


@router.get("/status")
async def status(lic: RateLimitedLicense) -> dict:
    return {"plugin": "pi-leads", "tier": lic.tier, "endpoints": ["score", "enrich"]}
