"""SEO Bot prompts — curated system + user messages for Claude.

This is the 'secret sauce' of Pi SEO Pro. Keep server-side only.
"""

import json
import re

from app.pi_seo.schemas import SeoBotGenerateRequest, SeoBotVariant

# ─────────────────────────────────────────────────────────────
# System prompt — sets voice + rules, language-agnostic base
# ─────────────────────────────────────────────────────────────
_SYSTEM_BASE = """Bạn là một SEO Copywriter chuyên nghiệp 10 năm kinh nghiệm, thành thạo \
tiếng Việt và tiếng Anh. Nhiệm vụ: viết SEO title + meta description cho bài viết WordPress.

NGUYÊN TẮC CỐT LÕI:
1. Title 50-60 ký tự (tính cả dấu cách). KHÔNG được vượt 65 ký tự.
2. Meta description 140-160 ký tự. KHÔNG được vượt 165 ký tự.
3. Focus keyword (nếu có) phải xuất hiện trong TITLE ở 1/2 đầu, và trong DESCRIPTION.
4. Title phải hấp dẫn, có action verb hoặc benefit rõ. KHÔNG chung chung.
5. Description phải có CTA ngầm (kêu gọi đọc tiếp, tìm hiểu, khám phá).
6. KHÔNG dùng clickbait rẻ tiền ("Bạn sẽ không tin...").
7. KHÔNG viết hoa toàn bộ. Dùng sentence case.
8. Với tiếng Việt: dùng dấu đầy đủ, không viết tắt, không dùng tiếng lóng.

OUTPUT FORMAT (BẮT BUỘC):
Trả về JSON object hợp lệ với structure:
{
  "variants": [
    {
      "title": "...",
      "description": "...",
      "og_image_prompt": "brief visual description for image generation",
      "slug_suggestion": "kebab-case-slug"
    }
  ]
}

KHÔNG kèm bất kỳ văn bản giải thích nào ngoài JSON. KHÔNG markdown code fence."""


# Tone adjustments appended to system
_TONE_GUIDE = {
    "professional": "Tone: chuyên nghiệp, lịch sự, khách quan. Tránh cảm thán.",
    "casual": "Tone: thân thiện, gần gũi, dùng ngôi 'bạn'. Câu ngắn gọn.",
    "friendly": "Tone: ấm áp, khuyến khích, dùng từ tích cực.",
    "authoritative": "Tone: uy tín, quyết đoán, trích dẫn số liệu nếu phù hợp.",
    "playful": "Tone: vui vẻ, sáng tạo, đôi khi dùng wordplay nhẹ.",
}

_AUDIENCE_GUIDE = {
    "general": "Audience: độc giả đại chúng, mọi trình độ.",
    "b2b": "Audience: doanh nghiệp, decision maker — nhấn mạnh ROI, efficiency.",
    "b2c": "Audience: consumer — nhấn mạnh benefit, emotion, giá.",
    "technical": "Audience: developer/technical — dùng thuật ngữ đúng, không đơn giản hóa.",
    "beginner": "Audience: người mới bắt đầu — tránh jargon, giải thích đơn giản.",
}


def build_seo_bot_prompt(req: SeoBotGenerateRequest) -> tuple[str, str]:
    """Build (system, user) messages for Claude."""
    system_parts = [_SYSTEM_BASE]
    if req.tone in _TONE_GUIDE:
        system_parts.append(_TONE_GUIDE[req.tone])
    if req.audience in _AUDIENCE_GUIDE:
        system_parts.append(_AUDIENCE_GUIDE[req.audience])

    if req.language == "vi":
        system_parts.append("Viết 100% bằng tiếng Việt có dấu.")
    elif req.language == "en":
        system_parts.append("Write 100% in English.")
    else:
        system_parts.append(
            "Detect language from title/excerpt — match output to that language."
        )

    system_parts.append(f"Số lượng variants cần trả về: {req.variants}.")

    user = _build_user_prompt(req)
    return "\n\n".join(system_parts), user


def _build_user_prompt(req: SeoBotGenerateRequest) -> str:
    parts = [
        "## Thông tin bài viết:",
        f"- Tiêu đề gốc: {req.post_title}",
    ]
    if req.focus_keyword:
        parts.append(f"- Focus keyword (BẮT BUỘC xuất hiện): **{req.focus_keyword}**")
    if req.excerpt:
        parts.append(f"- Mô tả ngắn: {req.excerpt}")
    if req.content_snippet:
        snippet = req.content_snippet[:1500]
        parts.append(f"- Nội dung (trích đoạn): {snippet}")

    parts.append("")
    parts.append(
        f"Hãy tạo {req.variants} variant title + meta description. "
        "Mỗi variant phải KHÁC NHAU rõ ràng (không đổi 1-2 từ). "
        "Trả về JSON đúng format đã quy định."
    )
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Parsing — extract structured output from Claude response
# ─────────────────────────────────────────────────────────────

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_seo_bot_output(text: str, expected: int = 1) -> list[SeoBotVariant]:
    """Parse Claude's response into SeoBotVariant list.

    Defensive parsing:
    - Strip markdown code fences (some models add them despite instructions)
    - Try raw JSON first, fallback to fenced
    - Validate each variant has title + description
    """
    text = text.strip()

    # Try fenced JSON first
    m = _JSON_FENCE_RE.search(text)
    raw = m.group(1) if m else text

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Last resort: find the first { ... } block
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON output: {e}") from e
        else:
            raise ValueError(f"No JSON found in output: {e}") from e

    if not isinstance(data, dict) or "variants" not in data:
        raise ValueError("Output missing 'variants' key")

    variants_raw = data["variants"]
    if not isinstance(variants_raw, list) or not variants_raw:
        raise ValueError("'variants' must be a non-empty list")

    variants: list[SeoBotVariant] = []
    for item in variants_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        desc = str(item.get("description", "")).strip()
        if not title or not desc:
            continue
        variants.append(
            SeoBotVariant(
                title=title[:70],  # hard cap
                description=desc[:180],
                og_image_prompt=item.get("og_image_prompt"),
                slug_suggestion=item.get("slug_suggestion"),
            )
        )

    if not variants:
        raise ValueError("No valid variants in output")
    return variants[:expected]
