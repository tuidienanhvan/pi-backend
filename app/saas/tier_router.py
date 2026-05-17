"""Public tier-spec endpoint — single source of truth for clients.

Mounted at `/v1/tiers/*`. Returns the canonical tier matrix from
`app.saas.tiers`. Clients (pi-api plugin, dashboard webapp, store webapp)
fetch from here instead of hardcoding numbers locally.

Caching: the response is deterministic per deploy. Clients should cache
for ~1 hour and invalidate on plugin/webapp update. The endpoint sets
`Cache-Control: public, max-age=3600`.
"""

from typing import Any

from fastapi import APIRouter, Response

from app.saas.tiers import all_tier_specs, public_tier_specs, tier_spec

router = APIRouter()


@router.get("/spec")
async def get_tier_spec(response: Response) -> dict[str, Any]:
    """Return the full tier matrix (all 4 tiers including enterprise).

    Response shape:
        {
          "tiers": [
            {
              "slug": "free",
              "display_name": "Free",
              "monthly_tokens": 50000,
              "max_sites": 1,
              "price_usd_per_month": 0,
              "priority_support": false,
              "features": ["seo_audit"]
            },
            ...
          ],
          "public_slugs": ["free", "pro", "max"]
        }
    """
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {
        "tiers": all_tier_specs(),
        "public_slugs": [spec["slug"] for spec in public_tier_specs()],
    }


@router.get("/spec/{tier_slug}")
async def get_one_tier_spec(tier_slug: str, response: Response) -> dict[str, Any]:
    """Return spec for a single tier. Unknown slugs fall back to `free`."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return tier_spec(tier_slug)
