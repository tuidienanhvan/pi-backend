"""Tier policy — SINGLE SOURCE OF TRUTH for the Pi Ecosystem.

ALL other code (pi-api plugin PHP, dashboard webapp, store webapp pricing
page, customer-facing docs) MUST reference these values — either by
importing from this module directly (Python callers) or by fetching the
`GET /v1/tiers/spec` endpoint (clients on other runtimes).

Adding/changing a tier's data: edit `TIER_MATRIX` below. The endpoint +
helpers are derived from it; do not hardcode the same number elsewhere.
"""

from typing import Any

# ─── Canonical tier matrix ───────────────────────────────────────
# Each tier entry includes everything a customer-facing surface needs:
#   display_name           — Cap-cased label for UI
#   monthly_tokens         — quota; -1 = unlimited
#   max_sites              — license activation cap; -1 = unlimited
#   price_usd_per_month    — 0 for free, None for custom enterprise quote
#   priority_support       — adds badge + skips queue
#   features               — list of feature slugs, or ["*"] for all
TIER_MATRIX: dict[str, dict[str, Any]] = {
    "free": {
        "display_name": "Free",
        "monthly_tokens": 50_000,
        "max_sites": 1,
        "price_usd_per_month": 0,
        "priority_support": False,
        "features": ["seo_audit"],
    },
    "pro": {
        "display_name": "Pro",
        "monthly_tokens": 1_000_000,
        "max_sites": 3,
        "price_usd_per_month": 29,
        "priority_support": False,
        "features": ["seo_audit", "ai_chatbot", "lead_pipeline", "analytics"],
    },
    "max": {
        "display_name": "Max",
        "monthly_tokens": 3_000_000,
        "max_sites": 10,
        "price_usd_per_month": 99,
        "priority_support": True,
        "features": [
            "seo_audit",
            "ai_chatbot",
            "lead_pipeline",
            "analytics",
            "multi_site",
            "white_label",
            "devops",
        ],
    },
    "enterprise": {
        "display_name": "Enterprise",
        "monthly_tokens": -1,        # unlimited
        "max_sites": -1,             # unlimited
        "price_usd_per_month": None, # custom quote
        "priority_support": True,
        "features": ["*"],           # all
    },
}

# ─── Legacy dict accessors — kept for backwards compat ───────────
# Derived from TIER_MATRIX so they cannot drift. Imports throughout the
# codebase already use these names; do not delete without sweeping refs.
TIER_FEATURES: dict[str, list[str]] = {
    tier: list(spec["features"]) for tier, spec in TIER_MATRIX.items()
}
TIER_TOKEN_QUOTA: dict[str, int | None] = {
    tier: (None if spec["monthly_tokens"] == -1 else spec["monthly_tokens"])
    for tier, spec in TIER_MATRIX.items()
}
TIER_MONTHLY_QUOTAS = TIER_TOKEN_QUOTA  # legacy alias
PUBLIC_TIERS = ["free", "pro", "max"]   # tiers shown on the pricing page


def normalize_tier(tier: str | None) -> str:
    value = (tier or "free").lower().strip()
    return value if value in TIER_MATRIX else "free"


def features_for_tier(tier: str | None) -> list[str]:
    return list(TIER_MATRIX[normalize_tier(tier)]["features"])


def monthly_quota_for_tier(tier: str | None) -> int:
    """Return monthly token quota. -1 = unlimited."""
    return int(TIER_MATRIX[normalize_tier(tier)]["monthly_tokens"])


def max_sites_for_tier(tier: str | None) -> int:
    """Return max license activations. -1 = unlimited."""
    return int(TIER_MATRIX[normalize_tier(tier)]["max_sites"])


def price_for_tier(tier: str | None) -> int | None:
    """Return monthly USD price. None = custom quote (enterprise)."""
    return TIER_MATRIX[normalize_tier(tier)]["price_usd_per_month"]


def tier_spec(tier: str) -> dict[str, Any]:
    """Return the full spec dict for one tier (slug included)."""
    t = normalize_tier(tier)
    return {"slug": t, **TIER_MATRIX[t]}


def all_tier_specs() -> list[dict[str, Any]]:
    """Return spec list for all tiers, in display order (free → enterprise)."""
    return [tier_spec(t) for t in TIER_MATRIX]


def public_tier_specs() -> list[dict[str, Any]]:
    """Return spec list for tiers shown on the public pricing page."""
    return [tier_spec(t) for t in PUBLIC_TIERS]
