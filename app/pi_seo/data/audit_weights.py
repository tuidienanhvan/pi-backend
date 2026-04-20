"""100-point SEO audit rules + weights.

Each rule is a callable: (analysis, focus_keyword) -> AuditIssue | None
Rules that pass return None; rules that fail return an AuditIssue with points_lost.

Total max loss = 100 (sum of all rules). Perfect score = 100.
"""

from collections.abc import Callable

from app.pi_seo.schemas import AuditIssue
from app.pi_seo.services.html_analyzer import HtmlAnalysis

Rule = Callable[[HtmlAnalysis, str], AuditIssue | None]

# ─────────────────────────────────────────────────────────────
# Meta rules (30 points)
# ─────────────────────────────────────────────────────────────


def _rule_title_present(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.title:
        return AuditIssue(
            code="title_missing",
            severity="error",
            category="meta",
            message="Không có <title> tag.",
            points_lost=10,
        )
    return None


def _rule_title_length(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.title:
        return None
    n = len(a.title)
    if n < 30:
        return AuditIssue(
            code="title_too_short",
            severity="warning",
            category="meta",
            message=f"Title chỉ {n} ký tự — nên 50-60.",
            points_lost=3,
        )
    if n > 65:
        return AuditIssue(
            code="title_too_long",
            severity="warning",
            category="meta",
            message=f"Title {n} ký tự — quá dài, Google cắt sau ~60.",
            points_lost=4,
        )
    return None


def _rule_title_has_keyword(a: HtmlAnalysis, kw: str) -> AuditIssue | None:
    if not kw or not a.title:
        return None
    if kw.lower() not in a.title.lower():
        return AuditIssue(
            code="title_missing_keyword",
            severity="warning",
            category="meta",
            message=f"Focus keyword '{kw}' không có trong title.",
            points_lost=5,
        )
    return None


def _rule_desc_present(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.meta_description:
        return AuditIssue(
            code="meta_desc_missing",
            severity="error",
            category="meta",
            message="Không có meta description.",
            points_lost=8,
        )
    return None


def _rule_desc_length(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.meta_description:
        return None
    n = len(a.meta_description)
    if n < 120:
        return AuditIssue(
            code="meta_desc_too_short",
            severity="warning",
            category="meta",
            message=f"Meta description {n} ký tự — nên 140-160.",
            points_lost=2,
        )
    if n > 170:
        return AuditIssue(
            code="meta_desc_too_long",
            severity="warning",
            category="meta",
            message=f"Meta description {n} ký tự — Google cắt sau ~160.",
            points_lost=2,
        )
    return None


def _rule_canonical_present(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.canonical:
        return AuditIssue(
            code="canonical_missing",
            severity="warning",
            category="technical",
            message="Không có canonical URL — có thể gây duplicate content.",
            points_lost=3,
        )
    return None


# ─────────────────────────────────────────────────────────────
# Content rules (30 points)
# ─────────────────────────────────────────────────────────────


def _rule_h1_exactly_one(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if a.h1_count == 0:
        return AuditIssue(
            code="h1_missing",
            severity="error",
            category="content",
            message="Không có thẻ H1.",
            points_lost=6,
        )
    if a.h1_count > 1:
        return AuditIssue(
            code="multiple_h1",
            severity="warning",
            category="content",
            message=f"Có {a.h1_count} thẻ H1 — chỉ nên 1.",
            points_lost=3,
        )
    return None


def _rule_h1_has_keyword(a: HtmlAnalysis, kw: str) -> AuditIssue | None:
    if not kw or not a.h1_texts:
        return None
    h1 = a.h1_texts[0].lower()
    if kw.lower() not in h1:
        return AuditIssue(
            code="h1_missing_keyword",
            severity="warning",
            category="content",
            message=f"H1 không chứa focus keyword '{kw}'.",
            points_lost=3,
        )
    return None


def _rule_word_count(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if a.word_count < 300:
        return AuditIssue(
            code="content_too_short",
            severity="warning",
            category="content",
            message=f"Nội dung chỉ {a.word_count} từ — nên >= 300 để xếp hạng.",
            points_lost=8,
        )
    return None


def _rule_h2_present(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if a.h2_count == 0 and a.word_count > 500:
        return AuditIssue(
            code="h2_missing",
            severity="warning",
            category="content",
            message="Bài dài không có H2 — chia section giúp đọc dễ hơn.",
            points_lost=4,
        )
    return None


def _rule_heading_hierarchy(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.heading_hierarchy_ok:
        return AuditIssue(
            code="heading_hierarchy_broken",
            severity="warning",
            category="content",
            message="Heading nhảy cấp (vd: H1→H3). Giữ thứ tự H1→H2→H3.",
            points_lost=3,
        )
    return None


def _rule_images_alt(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if a.img_total == 0:
        return None
    if a.img_missing_alt > 0:
        return AuditIssue(
            code="images_missing_alt",
            severity="warning",
            category="content",
            message=f"{a.img_missing_alt}/{a.img_total} ảnh thiếu alt text.",
            points_lost=min(6, a.img_missing_alt),
        )
    return None


# ─────────────────────────────────────────────────────────────
# Social / schema rules (20 points)
# ─────────────────────────────────────────────────────────────


def _rule_og_title(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.og_title:
        return AuditIssue(
            code="og_title_missing",
            severity="warning",
            category="social",
            message="Thiếu og:title — ảnh hưởng share Facebook/LinkedIn.",
            points_lost=4,
        )
    return None


def _rule_og_image(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.og_image:
        return AuditIssue(
            code="og_image_missing",
            severity="warning",
            category="social",
            message="Thiếu og:image — share sẽ không có thumbnail.",
            points_lost=5,
        )
    return None


def _rule_twitter_card(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.twitter_card:
        return AuditIssue(
            code="twitter_card_missing",
            severity="info",
            category="social",
            message="Thiếu twitter:card meta.",
            points_lost=2,
        )
    return None


def _rule_schema_present(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if not a.has_schema:
        return AuditIssue(
            code="schema_missing",
            severity="warning",
            category="social",
            message="Không có JSON-LD schema — thêm Article/Product tuỳ loại.",
            points_lost=6,
        )
    return None


def _rule_robots_ok(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if "noindex" in a.robots.lower():
        return AuditIssue(
            code="robots_noindex",
            severity="error",
            category="technical",
            message="Trang có noindex — KHÔNG index trên Google!",
            points_lost=20,
        )
    return None


# ─────────────────────────────────────────────────────────────
# Technical rules (20 points)
# ─────────────────────────────────────────────────────────────


def _rule_internal_links(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if a.links_internal == 0 and a.word_count > 300:
        return AuditIssue(
            code="no_internal_links",
            severity="warning",
            category="technical",
            message="Không có internal link — giảm crawl + authority.",
            points_lost=4,
        )
    return None


def _rule_external_links(a: HtmlAnalysis, _kw: str) -> AuditIssue | None:
    if a.links_external == 0 and a.word_count > 500:
        return AuditIssue(
            code="no_external_links",
            severity="info",
            category="technical",
            message="Không có external link — liên kết nguồn uy tín giúp E-E-A-T.",
            points_lost=2,
        )
    return None


# ─────────────────────────────────────────────────────────────
# Final rule list — ORDER MATTERS for UI grouping
# ─────────────────────────────────────────────────────────────

AUDIT_RULES: list[Rule] = [
    # Technical kill-switch
    _rule_robots_ok,
    # Meta
    _rule_title_present,
    _rule_title_length,
    _rule_title_has_keyword,
    _rule_desc_present,
    _rule_desc_length,
    _rule_canonical_present,
    # Content
    _rule_h1_exactly_one,
    _rule_h1_has_keyword,
    _rule_word_count,
    _rule_h2_present,
    _rule_heading_hierarchy,
    _rule_images_alt,
    # Social
    _rule_og_title,
    _rule_og_image,
    _rule_twitter_card,
    _rule_schema_present,
    # Technical
    _rule_internal_links,
    _rule_external_links,
]


def grade_for_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"
