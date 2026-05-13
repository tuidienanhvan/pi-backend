"""Source-plugin whitelist for AI usage attribution.

Each AI request hitting /v1/ai/complete declares a `source_plugin`
identifying the calling product (pi-seo, pi-chatbot, pi-leads, ...).
This module enforces a closed whitelist so customers cannot inject
arbitrary labels into AiUsage analytics or billing reports.

Added by T-20260513-001 — AI Provider Routing Optimization.
"""

from __future__ import annotations

from app.core.exceptions import PiException

# Authoritative set of accepted source plugins.
# To register a new plugin: add to this set + create a release note.
ALLOWED_SOURCE_PLUGINS: frozenset[str] = frozenset(
    {
        "pi-seo",       # SEO bot, content audit, keyword research
        "pi-chatbot",   # site chatbot widget
        "pi-leads",     # lead-gen forms / capture flows
        "pi-content",   # AI article writer (future)
        "pi-internal",  # admin tools (dashboard, store-admin direct test)
    }
)


class InvalidSourcePlugin(PiException):
    def __init__(self, given: str) -> None:
        super().__init__(
            status_code=400,
            code="invalid_source_plugin",
            message=(
                f"Unknown source_plugin '{given}'. "
                f"Allowed: {sorted(ALLOWED_SOURCE_PLUGINS)}"
            ),
        )


def validate_source_plugin(name: str | None) -> str:
    """Normalize + validate a source_plugin label.

    Returns the canonical string on success, raises InvalidSourcePlugin
    on unknown value. Empty input maps to "pi-internal" for backward
    compatibility with calls that omit the header.
    """
    if not name:
        return "pi-internal"
    canonical = name.strip().lower()
    if canonical not in ALLOWED_SOURCE_PLUGINS:
        raise InvalidSourcePlugin(name)
    return canonical


def is_valid(name: str | None) -> bool:
    """Non-raising check — useful for soft filters in analytics."""
    if not name:
        return False
    return name.strip().lower() in ALLOWED_SOURCE_PLUGINS
