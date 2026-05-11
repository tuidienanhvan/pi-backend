"""Tier-to-feature policy for connected WordPress tenants."""

TIER_FEATURES: dict[str, list[str]] = {
    "free": ["seo_audit"],
    "pro": ["ai_chatbot", "seo_audit", "lead_pipeline", "analytics"],
    "max": [
        "ai_chatbot",
        "seo_audit",
        "lead_pipeline",
        "analytics",
        "multi_site",
        "white_label",
        "devops",
    ],
    "enterprise": ["*"],
}

TIER_TOKEN_QUOTA: dict[str, int | None] = {
    "free": 50_000,
    "pro": 1_000_000,
    "max": 3_000_000,
    "enterprise": None,
}

TIER_MONTHLY_QUOTAS = TIER_TOKEN_QUOTA
PUBLIC_TIERS = ["free", "pro", "max"]


def normalize_tier(tier: str | None) -> str:
    value = (tier or "free").lower().strip()
    return value if value in TIER_FEATURES else "free"


def features_for_tier(tier: str | None) -> list[str]:
    return list(TIER_FEATURES[normalize_tier(tier)])


def monthly_quota_for_tier(tier: str | None) -> int:
    quota = TIER_TOKEN_QUOTA[normalize_tier(tier)]
    return quota if quota is not None else -1
