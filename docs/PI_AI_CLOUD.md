# Pi AI Cloud — Token Economy

**The primary revenue engine of the Pi ecosystem.**

> Pi AI Provider (plugin) stays FREE forever. Pi AI Cloud (this service) sells **tokens**.
> Customers pay for tokens, not providers.

---

## Business model in one diagram

```
┌─────────────────────────────────┐     buy tokens ($10 = 100k)
│  End customer (WordPress site)  │ ─────────────────────────────┐
└─────────────────────────────────┘                              ▼
         │ Pi plugin calls                                ┌──────────────┐
         │ /v1/ai/complete                               │   Stripe     │
         ▼                                               └──────┬───────┘
┌─────────────────────────────────┐        webhook credits     │
│  Pi Backend (FastAPI)           │ ◄──────────────────────────┘
│  ┌───────────────────────────┐  │
│  │ Wallet ledger — debit     │  │  $0 cost per call (free providers)
│  │ Router — pick provider    │──┼──►  Groq, Gemini, Cohere, Mistral, …
│  │ Adapter — call upstream   │  │
│  └───────────────────────────┘  │  Fallback (quality='best')
└─────────────────────────────────┘ ──►  Anthropic / OpenAI (paid)
       ↓ response + balance
       Pi plugin updates UI
```

**Pi's margin per $1 customer spend:**
- 90%+ if served by free providers (Groq, Gemini, etc.)
- 40-60% if fallback to paid (Claude/GPT-4)
- Weighted average target: **85% gross margin**

---

## Token pricing (consumer-facing)

| Pack | Tokens | Price (USD) | Price per 100k | Discount |
|---|---|---|---|---|
| Starter | 10,000 | $1.00 | $10.00 | — |
| **Popular** | **100,000** | **$9.00** | **$9.00** | 10% |
| Pro | 500,000 | $35.00 | $7.00 | 30% |
| Agency | 1,000,000 | $59.00 | $5.90 | 41% |
| Enterprise | 5,000,000 | $249.00 | $4.98 | 50% |

Prices set in `app/pi_ai_cloud/services/wallet.py` → `TOPUP_PACKS`.

**Free tier bonus:** Every new license gets **1,000 tokens** on signup.

---

## Internal economics

### Exchange rate (Pi tokens ↔ upstream tokens)

Each provider row has `pi_tokens_per_input` + `pi_tokens_per_output`.
We charge more Pi tokens than raw model-tokens to protect margin on paid fallbacks:

| Provider | Cost per 1M in/out ($) | Pi tokens per upstream input token | Pi tokens per upstream output token |
|---|---|---|---|
| Groq Llama 70B (free) | $0 / $0 | 1.0 | 1.5 |
| Gemini 2 Flash (free) | $0 / $0 | 1.0 | 1.5 |
| Mistral Small (free) | $0 / $0 | 1.0 | 1.5 |
| Cohere Command (free) | $0 / $0 | 1.0 | 1.5 |
| **Claude Sonnet (paid fallback)** | $3 / $15 | **3.0** | **5.0** |
| **GPT-4o (paid fallback)** | $5 / $15 | **5.0** | **5.0** |

### Example call costs

A typical SEO Bot generate request: ~500 input + 300 output = 800 tokens.

| Routed to | Pi tokens charged | Price to customer | Pi cost | Pi margin |
|---|---|---|---|---|
| Groq (free) | 500 + 300×1.5 = **950** | ~$0.085 | **$0** | **100%** |
| Claude (paid) | 500×3 + 300×5 = **3,000** | ~$0.27 | $0.006 | 97.8% |

→ Router prefers free tier — margin maxed.

---

## Provider routing algorithm

Located in `app/pi_ai_cloud/services/router.py`.

```
1. Customer sends POST /v1/ai/complete with quality='balanced'
2. Router picks candidates where:
     - is_enabled = true
     - health_status != 'down'
3. Order by:
     - priority ASC (lower = tried first)
     - tier ASC ('free' before 'paid' within same priority)
4. For each candidate:
     a. Try adapter.complete()
     b. Success → mark_success → charge wallet → return
     c. Failure → mark_failure (circuit breaker at 5 consecutive) → try next
5. All failed → return 502 ai_provider_error
```

**Quality tiers:**
- `fast` — free providers only, short wait
- `balanced` (default) — free first, paid fallback only if ALL free down
- `best` — paid first (Claude/GPT-4), fallback to free

---

## Single currency, multi-plugin

The killer feature: **one wallet, all Pi plugins.**

```
Customer buys 100k tokens
   ↓
Pi SEO uses 950 tokens   (SEO Bot generate)
Pi Chatbot uses 8,000    (RAG query)
Pi Leads uses 2,500      (AI lead scoring)
────────────────────────
Balance: 88,550 remaining
```

Every AI call — regardless of source plugin — deducts from the same wallet.
Customer tops up once, uses everywhere.

This is the **ecosystem lock-in** — moving away from Pi means re-integrating AI in every plugin.

---

## Admin operations

### Seed providers after first deploy

```bash
docker compose exec api python -m scripts.seed_ai_providers
```

This populates the `ai_providers` table with 5 free + 2 paid providers. Set API keys in `.env`:

```
PI_AI_KEY_GROQ_LLAMA_70B_FREE=gsk_...
PI_AI_KEY_GEMINI_2_FLASH_FREE=AIza...
PI_AI_KEY_MISTRAL_SMALL_FREE=...
...
```

### Manual token grant (for support / refund)

```python
# In a Python shell / admin CLI (to be written):
from app.core.db import AsyncSessionLocal
from app.pi_ai_cloud.services.wallet import WalletService
from app.shared.license.service import LicenseService

async with AsyncSessionLocal() as db:
    lic_svc = LicenseService(db)
    lic = await lic_svc.get_by_key("pi_abc...")
    wallet_svc = WalletService(db)
    wallet = await wallet_svc.get_or_create(lic)
    await wallet_svc.topup(
        wallet, 50_000,
        op="admin_adjust",
        note="Support ticket #123 — refund"
    )
    await db.commit()
```

### Monitor margin

Query `ai_usage` for Pi's upstream cost vs charged Pi tokens:

```sql
SELECT
  source_plugin,
  SUM(pi_tokens_charged) / 100000.0 * 9 AS revenue_usd,
  SUM(upstream_cost_cents) / 100.0       AS upstream_cost_usd,
  1 - SUM(upstream_cost_cents)::float / NULLIF(SUM(pi_tokens_charged) / 100000.0 * 900, 0) AS margin_pct
FROM ai_usage
WHERE created_at > now() - interval '30 days'
GROUP BY source_plugin
ORDER BY revenue_usd DESC;
```

---

## API reference (customer-facing)

### `POST /v1/ai/complete`
Main paid endpoint. Consumes tokens.

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Summarise: ..."}
  ],
  "max_tokens": 500,
  "temperature": 0.7,
  "quality": "balanced",
  "source_plugin": "pi-seo",
  "source_endpoint": "seo_bot.generate"
}
```

Response:
```json
{
  "success": true,
  "text": "The article is about ...",
  "pi_tokens_charged": 420,
  "wallet_balance_after": 99580,
  "input_tokens": 120,
  "output_tokens": 200,
  "provider_used": "groq-llama-70b-free"
}
```

Errors:
- `402 insufficient_tokens` — wallet empty, top up needed
- `502 ai_provider_error` — all providers failed

### `GET /v1/ai/wallet`
Return current balance + lifetime stats.

### `GET /v1/ai/ledger?limit=50&offset=0`
Transaction history.

### `POST /v1/ai/topup/checkout`
Creates a Stripe Checkout session, returns redirect URL.

```json
{
  "pack": "100k",
  "success_url": "https://customersite.com/billing?ok=1",
  "cancel_url": "https://customersite.com/billing?cancel=1"
}
```

### `GET /v1/ai/topup/packs`
List available token packs + prices.

### `POST /v1/ai/stripe/webhook` (no auth)
Stripe calls this on `checkout.session.completed`. Credits the wallet.

### `GET /v1/ai/providers`
Transparency — shows which providers Pi uses, but **not** keys.

---

## Security & abuse prevention

1. **Pre-flight balance check** — fail fast before calling upstream
2. **Minimum 1 token charge** — prevent 0-cost exploit
3. **Daily limit** (optional per wallet) — kill-switch for runaway loops
4. **Idempotency** — Stripe webhook uses `session_id` as reference_id
5. **Signed webhooks** — Stripe signature verified before crediting
6. **Rate limits** (via `core/deps.py`) — 10 req/min burst

---

## Why customers prefer this model

- **No per-API-key headaches** — they don't manage Anthropic, OpenAI, Gemini keys
- **Predictable pricing** — "$10 = 100k tokens" is simpler than "$X per million input + $Y per million output"
- **Works everywhere** — plugin ships with a single `PI_API_KEY`, not 20 keys
- **Upgrades without migration** — when Pi adds a new model, customer just benefits

---

## Why Pi profits

- Most traffic routes to free tier → **near-zero variable cost**
- Bulk tokens have discounts → encourages prepay → **cash up front**
- Single wallet across plugins → **ecosystem lock-in**
- Upstream pricing is opaque to customer → Pi can renegotiate without UI change
- When a free provider quota resets, Pi captures all savings

**Target: $10 revenue → $1 upstream cost → $9 profit per customer per month.**

With 1,000 active customers spending $10/mo avg → **$108k/year gross profit on ~$120k revenue.**
