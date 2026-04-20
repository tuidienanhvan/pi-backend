"""100-point SEO audit scorer — weights loaded from prompts module."""

import re
from dataclasses import asdict

from app.pi_seo.data.audit_weights import AUDIT_RULES, grade_for_score
from app.pi_seo.schemas import AuditIssue, AuditRunResponse
from app.pi_seo.services.html_analyzer import HtmlAnalysis, analyze_html


def run_audit(
    *,
    title: str,
    meta_description: str,
    focus_keyword: str,
    html: str,
    url: str = "",
) -> AuditRunResponse:
    """Run all audit rules and return score + issues."""
    # Parse HTML; prefer explicit title/meta if provided
    analysis = analyze_html(html, url)
    if title:
        analysis = analysis.__class__(**{**asdict(analysis), "title": title})
    if meta_description:
        analysis = analysis.__class__(
            **{**asdict(analysis), "meta_description": meta_description}
        )

    issues: list[AuditIssue] = []
    score = 100

    for rule in AUDIT_RULES:
        issue = rule(analysis, focus_keyword)
        if issue is not None:
            issues.append(issue)
            score -= issue.points_lost

    score = max(0, min(100, score))

    return AuditRunResponse(
        success=True,
        score=score,
        grade=grade_for_score(score),
        issues=issues,
        stats={
            "word_count": analysis.word_count,
            "h1_count": analysis.h1_count,
            "h2_count": analysis.h2_count,
            "img_total": analysis.img_total,
            "img_missing_alt": analysis.img_missing_alt,
            "links_internal": analysis.links_internal,
            "links_external": analysis.links_external,
            "has_schema": analysis.has_schema,
            "schema_types": analysis.schema_types,
        },
    )


def analyze_content(content: str, focus_keyword: str = "", language: str = "auto") -> dict:
    """Lightweight content analysis — readability, density, structure."""
    import textstat
    from langdetect import detect, LangDetectException

    # Detect language
    if language == "auto":
        try:
            language = detect(content[:500]) if len(content) > 30 else "unknown"
        except LangDetectException:
            language = "unknown"

    text = re.sub(r"<[^>]+>", " ", content)
    text = re.sub(r"\s+", " ", text).strip()

    words = text.split()
    word_count = len(words)

    # Sentence / paragraph
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentence_count = len([s for s in sentences if s.strip()])
    paragraphs = [p for p in content.split("\n") if p.strip()]
    paragraph_count = max(1, len(paragraphs))

    avg_sent_len = word_count / max(1, sentence_count)

    # Readability — Flesch Reading Ease (higher = easier)
    try:
        readability = float(textstat.flesch_reading_ease(text))
    except Exception:  # noqa: BLE001
        readability = 0.0
    grade = _readability_grade(readability)

    # Keyword density
    kw = focus_keyword.strip().lower()
    kw_count = text.lower().count(kw) if kw else 0
    density = (kw_count / word_count * 100) if word_count > 0 else 0.0

    # Recommendations
    recs: list[str] = []
    if word_count < 300:
        recs.append(f"Bài viết chỉ {word_count} từ — nên >= 300 từ cho SEO.")
    if avg_sent_len > 25:
        recs.append(f"Câu trung bình {avg_sent_len:.0f} từ — quá dài, khó đọc.")
    if readability < 40:
        recs.append("Độ dễ đọc thấp — chia nhỏ câu, đơn giản từ ngữ.")
    if kw and density < 0.5:
        recs.append(f"Keyword density {density:.2f}% — quá thấp, nên 0.5-2.5%.")
    if kw and density > 3.0:
        recs.append(f"Keyword density {density:.2f}% — quá cao, có thể bị coi là spam.")
    if paragraph_count < 3:
        recs.append("Chia nội dung thành nhiều đoạn (ít nhất 3) để dễ đọc hơn.")

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "avg_sentence_length": round(avg_sent_len, 1),
        "readability_score": round(readability, 1),
        "readability_grade": grade,
        "keyword_density": round(density, 2),
        "keyword_count": kw_count,
        "language_detected": language,
        "recommendations": recs,
    }


def _readability_grade(score: float) -> str:
    if score >= 90:
        return "Very Easy"
    if score >= 70:
        return "Easy"
    if score >= 60:
        return "Fairly Easy"
    if score >= 50:
        return "Fairly Difficult"
    if score >= 30:
        return "Difficult"
    return "Very Difficult"
