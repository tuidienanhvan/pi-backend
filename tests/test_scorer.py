"""Unit tests for audit scorer — pure functions, no DB."""

from app.pi_seo.services.scorer import analyze_content, run_audit


GOOD_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Guide to WordPress SEO — Everything You Need to Know</title>
  <meta name="description" content="Comprehensive guide to WordPress SEO covering meta tags, schema, sitemaps, and audit strategies to rank your blog higher in Google search results.">
  <link rel="canonical" href="https://example.com/seo-guide/">
  <meta property="og:title" content="Guide to WordPress SEO">
  <meta property="og:description" content="...">
  <meta property="og:image" content="https://example.com/og.jpg">
  <meta name="twitter:card" content="summary_large_image">
  <script type="application/ld+json">{"@type":"Article"}</script>
</head>
<body>
  <h1>Guide to WordPress SEO</h1>
  <h2>Section 1</h2>
  <p>""" + ("word " * 400) + """</p>
  <img src="a.jpg" alt="alt a">
  <a href="https://example.com/post-2">internal</a>
  <a href="https://external.com">external</a>
</body>
</html>
"""


def test_good_html_scores_high() -> None:
    res = run_audit(
        title="Guide to WordPress SEO — Everything You Need to Know",
        meta_description="Comprehensive guide to WordPress SEO covering meta tags, schema, sitemaps, and audit strategies to rank your blog higher in Google search results.",
        focus_keyword="WordPress SEO",
        html=GOOD_HTML,
        url="https://example.com/seo-guide/",
    )
    assert res.score >= 80, f"Expected >=80, got {res.score}. Issues: {res.issues}"
    assert res.grade in ("A", "B")


def test_empty_html_scores_low() -> None:
    res = run_audit(
        title="",
        meta_description="",
        focus_keyword="test",
        html="<html><body></body></html>",
    )
    assert res.score < 50
    codes = {i.code for i in res.issues}
    assert "title_missing" in codes
    assert "meta_desc_missing" in codes
    assert "h1_missing" in codes


def test_noindex_is_fatal() -> None:
    html = '<html><head><meta name="robots" content="noindex"></head></html>'
    res = run_audit(title="T", meta_description="D", focus_keyword="", html=html)
    codes = {i.code for i in res.issues}
    assert "robots_noindex" in codes


def test_content_analyze_word_count() -> None:
    text = " ".join(["word"] * 100)
    res = analyze_content(content=text, focus_keyword="word")
    assert res["word_count"] == 100
    assert res["keyword_count"] == 100
    assert res["keyword_density"] > 0


def test_content_analyze_low_word_count_recommends() -> None:
    res = analyze_content(content="Short content.", focus_keyword="")
    assert any("300 từ" in r for r in res["recommendations"])
