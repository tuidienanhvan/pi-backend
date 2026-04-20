"""Pi SEO — all DTOs in one place (request/response bodies)."""

from typing import Literal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────
# SEO Bot — AI-generated title + meta description
# ─────────────────────────────────────────────────────────────

Tone = Literal["professional", "casual", "friendly", "authoritative", "playful"]
Audience = Literal["general", "b2b", "b2c", "technical", "beginner"]
Language = Literal["vi", "en", "auto"]


class SeoBotGenerateRequest(BaseModel):
    site_url: str
    post_id: int
    post_title: str = Field(..., min_length=1, max_length=500)
    focus_keyword: str = Field("", max_length=100)
    excerpt: str = Field("", max_length=2000)
    content_snippet: str = Field("", max_length=4000)
    tone: Tone = "professional"
    audience: Audience = "general"
    language: Language = "auto"
    variants: int = Field(1, ge=1, le=5)


class SeoBotVariant(BaseModel):
    title: str
    description: str
    og_image_prompt: str | None = None
    slug_suggestion: str | None = None


class SeoBotGenerateResponse(BaseModel):
    success: bool
    variants: list[SeoBotVariant]
    tokens_used: int = 0
    model: str = ""


class SeoBotBulkRequest(BaseModel):
    site_url: str
    posts: list[dict] = Field(..., max_length=50)
    tone: Tone = "professional"
    audience: Audience = "general"
    language: Language = "auto"


class SeoBotBulkResponse(BaseModel):
    success: bool
    task_id: str
    queued: int
    message: str


# ─────────────────────────────────────────────────────────────
# Audit — 100-point SEO scoring + content analysis
# ─────────────────────────────────────────────────────────────


class AuditRunRequest(BaseModel):
    site_url: str
    post_id: int | None = None
    title: str = ""
    meta_description: str = ""
    focus_keyword: str = ""
    html: str = Field("", max_length=500_000)
    url: str = ""


class AuditIssue(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    category: Literal["meta", "content", "technical", "readability", "social"]
    message: str
    points_lost: int


class AuditRunResponse(BaseModel):
    success: bool
    score: int = Field(..., ge=0, le=100)
    grade: Literal["A", "B", "C", "D", "F"]
    issues: list[AuditIssue]
    stats: dict


class ContentAnalyzeRequest(BaseModel):
    content: str = Field(..., min_length=50, max_length=200_000)
    focus_keyword: str = ""
    language: str = "auto"


class ContentAnalyzeResponse(BaseModel):
    success: bool
    word_count: int
    sentence_count: int
    paragraph_count: int
    avg_sentence_length: float
    readability_score: float
    readability_grade: str
    keyword_density: float
    keyword_count: int
    language_detected: str
    recommendations: list[str]


# ─────────────────────────────────────────────────────────────
# Schema Library — curated JSON-LD templates
# ─────────────────────────────────────────────────────────────


class SchemaTemplate(BaseModel):
    id: str
    label: str
    category: str
    schema_type: str
    description: str
    json_ld: str
    tier_required: str = "free"


class SchemaTemplatesResponse(BaseModel):
    success: bool
    templates: list[SchemaTemplate]
    total: int
