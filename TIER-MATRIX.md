# Tier Matrix — Single Source of Truth

Canonical reference for the Pi Ecosystem subscription tiers. ALL surfaces
that show tier info to customers — pi-api plugin, dashboard webapp,
store webapp pricing page, docs — MUST derive their values from here
(via the `/v1/tiers/spec` endpoint), not hardcode them.

> **Code reference**: [`app/saas/tiers.py`](./app/saas/tiers.py) — the
> dict `TIER_MATRIX` is the literal source. Edit there → all consumers
> pick up automatically via the API.

---

## 1. Tier reference table

| | **Free** | **Pro** | **Max** | **Enterprise** |
|---|---|---|---|---|
| **Price (USD/month)** | $0 | $29 | $99 | Custom quote |
| **Monthly tokens** | 50,000 | 1,000,000 | 3,000,000 | Unlimited |
| **Max site activations** | 1 | 3 | 10 | Unlimited |
| **Priority support** | — | — | ✅ | ✅ |
| **Features** | seo_audit | + ai_chatbot<br>+ lead_pipeline<br>+ analytics | + multi_site<br>+ white_label<br>+ devops | All (`*`) |

### Public vs internal tiers

- **Public** (shown on pricing page): `free`, `pro`, `max`
- **Internal** (sales-led only): `enterprise`

The pricing page should query `GET /v1/tiers/spec` and filter to
`public_slugs` from the response.

---

## 2. Feature slug reference

| Slug | Description | Tier minimum |
|---|---|---|
| `seo_audit` | SEO scoring + recommendations | Free |
| `ai_chatbot` | AI chatbot for site | Pro |
| `lead_pipeline` | Lead capture + CRM | Pro |
| `analytics` | Traffic + conversion dashboards | Pro |
| `multi_site` | Manage > 3 sites from one license | Max |
| `white_label` | Strip Pi branding from chatbot | Max |
| `devops` | API key vault, cron scheduler, db explorer | Max |

`enterprise` tier returns `["*"]` (all features enabled). Backend
feature check should treat `"*"` as "any feature allowed".

---

## 3. API endpoint

### `GET /v1/tiers/spec`

Public. No auth required. `Cache-Control: public, max-age=3600`.

**Response:**
```json
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
    {
      "slug": "pro",
      "display_name": "Pro",
      "monthly_tokens": 1000000,
      "max_sites": 3,
      "price_usd_per_month": 29,
      "priority_support": false,
      "features": ["seo_audit", "ai_chatbot", "lead_pipeline", "analytics"]
    },
    {
      "slug": "max",
      "display_name": "Max",
      "monthly_tokens": 3000000,
      "max_sites": 10,
      "price_usd_per_month": 99,
      "priority_support": true,
      "features": ["seo_audit", "ai_chatbot", "lead_pipeline", "analytics", "multi_site", "white_label", "devops"]
    },
    {
      "slug": "enterprise",
      "display_name": "Enterprise",
      "monthly_tokens": -1,
      "max_sites": -1,
      "price_usd_per_month": null,
      "priority_support": true,
      "features": ["*"]
    }
  ],
  "public_slugs": ["free", "pro", "max"]
}
```

**Semantic notes:**
- `monthly_tokens: -1` → unlimited (no enforcement)
- `max_sites: -1` → unlimited
- `price_usd_per_month: null` → custom quote (contact sales)
- `features: ["*"]` → all features unlocked

### `GET /v1/tiers/spec/{tier_slug}`

Single-tier lookup. Unknown slugs return the `free` spec (defensive).
Same cache headers.

---

## 4. Internal helpers (Python)

```python
from app.saas.tiers import (
    TIER_MATRIX,            # the dict
    tier_spec,              # tier_spec("pro") → {"slug": "pro", ...}
    all_tier_specs,         # list of 4 spec dicts
    public_tier_specs,      # list of 3 spec dicts (no enterprise)
    features_for_tier,      # ["ai_chatbot", ...]
    monthly_quota_for_tier, # int (or -1)
    max_sites_for_tier,     # int (or -1)
    price_for_tier,         # int or None
    normalize_tier,         # "PRO" → "pro", unknown → "free"
)
```

The legacy aliases `TIER_FEATURES` and `TIER_TOKEN_QUOTA` are derived
from `TIER_MATRIX` and remain importable for existing callers.

---

## 5. Consumer integration roadmap

| Consumer | Status | Tracking |
|---|---|---|
| `pi-backend` (server enforcement) | ✅ Done | T-010 Phase B |
| `pi-backend` API endpoint `/v1/tiers/spec` | ✅ Done | T-010 Phase B |
| `pi-backend` `TIER-MATRIX.md` doc | ✅ Done | T-010 Phase B (this file) |
| `pi-backend` `PRODUCTION-SETUP.md` updated | ✅ Done | T-010 Phase B |
| `plugins/pi-api` `Settings::getTokenQuota()` → fetch from endpoint | 🟡 Pending | T-010 Phase C (queued) |
| `plugins/pi-api` `DOCS.md` updated to match | 🟡 Pending | T-010 Phase C |
| `pi-dashboard-webapp` `useTierSpec()` hook + 7 UI components synced | 🟡 Pending | T-010 Phase D |
| `pi-store-webapp` 5 pricing components synced | 🟡 Pending | T-010 Phase E |
| Admin license tier → enterprise (one-time) | ✅ Done | Manual SQL on Neon |

---

## 6. Edge cases & policies

### Downgrade behavior
When a customer downgrades (e.g. Pro → Free):
- Features list shrinks immediately — feature checks reject unauthorized calls
- Monthly token quota drops at next billing cycle (don't claw back mid-cycle)
- Active license stays valid until end of current paid period
- `max_sites` check: if customer has more sites activated than new tier allows, existing remain active but no new activations until count drops or upgrade

### Upgrade behavior
- Immediate effect on features + quota
- Stripe handles prorated billing (when billing wired up)
- Existing usage counter for the month keeps accumulating (don't reset)

### Adding a new tier
1. Add entry to `TIER_MATRIX` in `app/saas/tiers.py`
2. Decide if it's public — add slug to `PUBLIC_TIERS` if yes
3. Add to feature → tier mapping in §2 above
4. Update `pi-api` plugin's tier whitelist in `Settings::normalizeTier()` (PHP-side validator)
5. No DB migration needed — `licenses.tier` is `String(16)` with no FK
6. Sync pricing page copy (store-webapp) — manual content review
7. Backend endpoint auto-includes the new tier

### Pricing changes
Only edit `price_usd_per_month` in `TIER_MATRIX`. The endpoint cache
expires hourly so customers see new pricing within ~1 hour. For
immediate effect: bump `pi_api_tier_spec` transient TTL in plugin.

### Removing a feature from a tier
1. Remove from `features` list in `TIER_MATRIX`
2. Customers on that tier lose access at next page load (UI re-fetches)
3. Backend feature check uses live spec — instant cutoff
4. Email customers about removed features ≥ 30 days before change

---

## 7. Verification

```bash
# After backend deploy:
curl -s https://pi-backend.up.railway.app/v1/tiers/spec | jq '.tiers[] | {slug, monthly_tokens, price_usd_per_month}'

# Should output:
# { "slug": "free",       "monthly_tokens": 50000,   "price_usd_per_month": 0 }
# { "slug": "pro",        "monthly_tokens": 1000000, "price_usd_per_month": 29 }
# { "slug": "max",        "monthly_tokens": 3000000, "price_usd_per_month": 99 }
# { "slug": "enterprise", "monthly_tokens": -1,      "price_usd_per_month": null }

# Cache header:
curl -sI https://pi-backend.up.railway.app/v1/tiers/spec | grep -i cache
# Expect: Cache-Control: public, max-age=3600
```

---

**Last updated**: 2026-05-17 (T-20260517-010 Phase B). Decisions made by user — see `.task-handoffs/active/T-20260517-010-*.md` §II.C.
