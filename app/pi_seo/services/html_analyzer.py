"""HTML analysis — extract meta tags, headings, images, links for audit."""

from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup


@dataclass
class HtmlAnalysis:
    title: str
    meta_description: str
    canonical: str
    robots: str
    og_title: str
    og_description: str
    og_image: str
    twitter_card: str
    h1_count: int
    h1_texts: list[str]
    h2_count: int
    heading_hierarchy_ok: bool
    img_total: int
    img_missing_alt: int
    links_internal: int
    links_external: int
    links_nofollow: int
    text_content: str
    word_count: int
    has_schema: bool
    schema_types: list[str]


def analyze_html(html: str, base_url: str = "") -> HtmlAnalysis:
    """Parse HTML and extract structured SEO-relevant data."""
    soup = BeautifulSoup(html or "", "lxml")

    # Meta tags
    title_tag = soup.find("title")
    title = title_tag.text.strip() if title_tag else ""

    desc = _meta(soup, "name", "description")
    canonical = _link(soup, "canonical")
    robots = _meta(soup, "name", "robots")
    og_title = _meta(soup, "property", "og:title")
    og_desc = _meta(soup, "property", "og:description")
    og_image = _meta(soup, "property", "og:image")
    twitter_card = _meta(soup, "name", "twitter:card")

    # Headings
    h1s = soup.find_all("h1")
    h1_texts = [h.get_text(strip=True) for h in h1s]
    h2s = soup.find_all("h2")

    # Heading hierarchy: h1 then h2+, no h3 before h2, etc.
    hierarchy_ok = _check_heading_hierarchy(soup)

    # Images
    imgs = soup.find_all("img")
    img_total = len(imgs)
    img_missing_alt = sum(1 for i in imgs if not (i.get("alt") or "").strip())

    # Links
    base_host = urlparse(base_url).hostname if base_url else ""
    internal = external = nofollow = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        if "nofollow" in (a.get("rel") or []):
            nofollow += 1
        parsed = urlparse(href)
        host = parsed.hostname or ""
        if not host or host == base_host:
            internal += 1
        else:
            external += 1

    # Content
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    text = soup.get_text(separator=" ", strip=True)
    word_count = len(text.split())

    # Schema
    schema_scripts = soup.find_all("script", type="application/ld+json")
    has_schema = len(schema_scripts) > 0
    schema_types: list[str] = []
    for s in schema_scripts:
        try:
            import json

            data = json.loads(s.string or "{}")
            if isinstance(data, dict):
                t = data.get("@type", "")
                if t:
                    schema_types.append(t if isinstance(t, str) else ",".join(t))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and (t := item.get("@type")):
                        schema_types.append(t if isinstance(t, str) else ",".join(t))
        except Exception:  # noqa: BLE001
            continue

    return HtmlAnalysis(
        title=title,
        meta_description=desc,
        canonical=canonical,
        robots=robots,
        og_title=og_title,
        og_description=og_desc,
        og_image=og_image,
        twitter_card=twitter_card,
        h1_count=len(h1s),
        h1_texts=h1_texts,
        h2_count=len(h2s),
        heading_hierarchy_ok=hierarchy_ok,
        img_total=img_total,
        img_missing_alt=img_missing_alt,
        links_internal=internal,
        links_external=external,
        links_nofollow=nofollow,
        text_content=text,
        word_count=word_count,
        has_schema=has_schema,
        schema_types=schema_types,
    )


def _meta(soup: BeautifulSoup, attr: str, value: str) -> str:
    tag = soup.find("meta", attrs={attr: value})
    return (tag.get("content") if tag else "") or ""


def _link(soup: BeautifulSoup, rel: str) -> str:
    tag = soup.find("link", rel=rel)
    return (tag.get("href") if tag else "") or ""


def _check_heading_hierarchy(soup: BeautifulSoup) -> bool:
    """Return True if headings never skip a level (h1→h3 is bad)."""
    levels = []
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        levels.append(int(h.name[1]))
    if not levels:
        return True
    prev = levels[0]
    for lvl in levels[1:]:
        if lvl > prev + 1:
            return False
        prev = lvl
    return True
