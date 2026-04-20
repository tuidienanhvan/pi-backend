# Pi Ecosystem — Full deployment guide

End-to-end checklist: từ zero đến production, bao gồm backend + admin/user dashboard + Pi SEO v2 plugin.

**Target:** Live system at **api.piwebagency.com** + **store.pi-ecosystem.com** + any customer WP site running `pi-seo-v2`.

---

## Architecture recap

```
Customer WP site (pi-seo-v2 plugin)
     │  Authorization: Bearer pi_xxx (license key)
     ▼
┌─────────────────────────────┐          ┌─────────────────────────┐
│  api.piwebagency.com        │ ◄──────► │  Stripe                 │
│  (pi-backend — Railway)     │          └─────────────────────────┘
│  FastAPI + Postgres + Redis │
│                             │          ┌─────────────────────────┐
│  Upstream AI providers ─────┼────────► │  Groq, Gemini, Mistral, │
│  (25 free + 2 paid)         │          │  Cohere, Together (free)│
└──────────────┬──────────────┘          └─────────────────────────┘
               │
               │ Authorization: Bearer <JWT>
               ▼
┌─────────────────────────────┐
│  store.pi-ecosystem.com     │
│  (pi-store-webapp — Vercel) │
│    /                public  │
│    /app/*           user    │
│    /admin/*         admin   │
└─────────────────────────────┘
```

---

## 0. Prerequisites

- [ ] **Domains** pointed:
  - `api.piwebagency.com` → (Railway target CNAME)
  - `store.pi-ecosystem.com` → (Vercel target CNAME)
- [ ] **Free AI provider accounts** created, API keys copied:
  - Groq: https://console.groq.com
  - Gemini: https://aistudio.google.com
  - Mistral: https://console.mistral.ai
  - Cohere: https://dashboard.cohere.com
  - Together: https://api.together.xyz
- [ ] **Stripe** account ready (test keys OK for staging):
  - https://dashboard.stripe.com → API keys
- [ ] **GitHub repo** created + code pushed (for Railway auto-deploy).

---

## 1. Deploy pi-backend to Railway

```bash
# 1.1 Install Railway CLI
npm i -g @railway/cli
railway login

# 1.2 From pi-backend dir
cd wp-content/pi-backend
railway init            # choose "Empty Project" or link GitHub repo
railway up              # first deploy (fails until DB attached)

# 1.3 Add Postgres + Redis plugins in Railway dashboard
#     Copy DATABASE_URL (prefix with postgresql+asyncpg://)
#     Copy REDIS_URL

# 1.4 Set env vars in Railway dashboard:
```

**Required env vars (Railway → Variables tab):**

```bash
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=<python -c "import secrets;print(secrets.token_hex(32))">
JWT_SECRET=<same command, different output>
APP_BASE_URL=https://api.piwebagency.com
APP_CORS_ORIGINS=https://store.pi-ecosystem.com,https://saigonhoreca.vn

DATABASE_URL=postgresql+asyncpg://...        # from Postgres plugin (change scheme)
REDIS_URL=${{Redis.REDIS_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}

# AI provider keys
PI_AI_KEY_GROQ_LLAMA_70B_FREE=gsk_...
PI_AI_KEY_GEMINI_2_FLASH_FREE=AIza...
PI_AI_KEY_MISTRAL_SMALL_FREE=...
PI_AI_KEY_COHERE_COMMAND_FREE=...
PI_AI_KEY_TOGETHER_LLAMA_FREE=...

# Stripe
STRIPE_SECRET_KEY=sk_live_...                # use sk_test_ for staging first
STRIPE_WEBHOOK_SECRET=whsec_...              # from Stripe dashboard

# Rate limits (override defaults if needed)
RATE_LIMIT_FREE_PER_MONTH=20
RATE_LIMIT_PRO_PER_MONTH=500
RATE_LIMIT_AGENCY_PER_MONTH=5000

LOG_LEVEL=INFO
SENTRY_DSN=                                  # optional, highly recommended
```

**Deploy:**

```bash
railway up
# Watches logs. Should see:
#   INFO alembic.runtime.migration - Running upgrade  -> 001_initial, initial schema
#   INFO alembic.runtime.migration - Running upgrade 001 -> 002_pi_ai_cloud
#   INFO alembic.runtime.migration - Running upgrade 002 -> 003_users
#   INFO pi_backend_starting
#   INFO Uvicorn running on 0.0.0.0:PORT
```

**Add custom domain:**
```
Railway → Settings → Domains → Custom → api.piwebagency.com
```

**Verify:**

```bash
curl https://api.piwebagency.com/health
# → {"status":"ok"}

curl https://api.piwebagency.com/ready
# → {"status":"ok","database":"ok","redis":"ok"}
```

---

## 2. Seed providers + create admin

Once backend is live:

```bash
# 2.1 Seed AI providers (7 rows: 5 free + 2 paid fallback)
railway run python -m scripts.seed_ai_providers

# 2.2 Create first admin user for the dashboard
railway run python -m scripts.create_admin \
    --email admin@piwebagency.com \
    --name "Pi Admin"
# Prompts for password. Pick something 12+ chars.
```

Remember the admin credentials — you'll sign in at `store.pi-ecosystem.com/login`.

---

## 3. Configure Stripe webhook

Stripe → **Developers** → **Webhooks** → **Add endpoint**:

- Endpoint URL: `https://api.piwebagency.com/v1/ai/stripe/webhook`
- Events: `checkout.session.completed`
- Copy the **Signing secret** → set `STRIPE_WEBHOOK_SECRET` in Railway.
- Redeploy Railway service.

Test checkout locally with Stripe CLI:
```bash
stripe listen --forward-to https://api.piwebagency.com/v1/ai/stripe/webhook
stripe trigger checkout.session.completed
# Check pi-backend logs for "wallet_topup" entry
```

---

## 4. Deploy pi-store-webapp to Vercel

```bash
cd wp-content/pi-store-webapp
npm install
npm run build

# Vercel:
npm i -g vercel
vercel
# Accept defaults; link to project.
```

**Env vars in Vercel dashboard (Settings → Environment Variables):**

```
VITE_PI_API_URL=https://api.piwebagency.com
VITE_LEAD_API_URL=/api/lead               # existing n8n proxy
N8N_WEBHOOK_URL=https://...               # if using lead form
N8N_SHARED_SECRET=...
```

**Add custom domain:**
```
Vercel → Project → Settings → Domains → store.pi-ecosystem.com
```

**Verify:**
- Visit `https://store.pi-ecosystem.com` → catalog renders
- Visit `/login` → login form renders
- Sign in with admin credentials → redirects to `/admin`
- Admin overview shows live stats (may be zero at first)

---

## 5. Create your first license + sell your first plugin

```bash
# 5.1 Create a test license
railway run python -m scripts.create_license \
    --plugin pi-seo-pro \
    --email customer@example.com \
    --tier pro \
    --max-sites 1 \
    --expires-days 365

# Output includes: Key: pi_abc123...
```

**Test flow:**
1. Copy the key to your Pi SEO v2 site (Plugins → Pi SEO v2 → paste license)
2. Activate — should call `/v1/license/verify` + `/v1/license/activate`
3. Try "AI SEO Bot" in a post edit screen → consumes tokens
4. Check wallet at `store.pi-ecosystem.com/app/wallet` — shows balance

---

## 6. Prepare plugin release ZIPs

```bash
# From wp-content/ root
cd "C:/Users/Administrator/Local Sites/saigonhouse/app/public/wp-content"

# Zip pi-seo-v2 with shared library
mkdir -p dist
zip -r dist/pi-seo-v2-2.0.0.zip \
    plugins-v2/pi-seo-v2 \
    plugins-v2/_shared
```

Upload via admin dashboard `/admin/releases` → pick plugin, version, tier, changelog, upload ZIP. Backend stores the file + hashes SHA-256.

Customer WP sites with v2 plugin will auto-detect updates via `/v1/updates/check/pi-seo-v2`.

---

## 7. Post-deploy smoke test checklist

Run through each item in production:

### Auth
- [ ] Signup creates user + returns JWT
- [ ] Login with wrong password → 401
- [ ] `GET /v1/auth/me` with JWT → returns user + license_count + token_balance
- [ ] JWT expires after 7 days

### License
- [ ] Admin creates license → customer receives key
- [ ] Plugin activates → site appears in `/admin/licenses`
- [ ] Revoke license → plugin's AI calls start returning 403

### Pi AI Cloud
- [ ] New signup gets 1,000 free tokens (bonus)
- [ ] `/v1/ai/complete` with `quality=balanced` picks Groq first (healthy)
- [ ] Wallet deducts correct tokens after call
- [ ] Ledger records the spend
- [ ] Stripe webhook credits wallet after payment (use test mode)
- [ ] Providers page shows 7 providers, all healthy

### Pi SEO v2
- [ ] Free site (no license) renders meta tags + sitemap + schema basic
- [ ] Pro license unlocks AI SEO Bot metabox
- [ ] AI Bot generates title/desc → tokens deducted
- [ ] Audit runs via `/v1/seo/audit/run` → returns score + issues
- [ ] Schema Pro templates load via `/v1/seo/schema/templates`

### Admin dashboard
- [ ] `/admin` shows revenue + active licenses + provider health
- [ ] `/admin/licenses` list loads, filter by tier works
- [ ] Create license modal → new key generated, can be copied
- [ ] Revoke license toggles status
- [ ] `/admin/providers` toggle works; failed providers show "degraded"
- [ ] `/admin/usage` shows per-plugin breakdown
- [ ] `/admin/releases` upload ZIP → appears in list

### User dashboard
- [ ] `/app` overview shows wallet + license + sites
- [ ] `/app/wallet` shows packs; clicking `Buy` redirects to Stripe
- [ ] After payment, `/app/ledger` shows the topup entry
- [ ] `/app/licenses` shows stats; license key can be copied

---

## 8. Monitoring + alerts

### Sentry (recommended)
```
pip install sentry-sdk  # already in pyproject.toml dev deps; promote to main
```

Set `SENTRY_DSN` env var. Auto-captures exceptions.

### Logs
Railway auto-captures stdout. View: Railway → Service → Deployments → (latest) → Logs.

Critical lines to alert on:
- `provider_circuit_open` — one provider down 5 times in a row
- `wallet_topup` — successful Stripe payment
- `provider_failed_trying_next` — fallback in action
- `unhandled_exception` — bug

### DB backups
Railway → Postgres plugin → Backups (daily snapshots auto). Download weekly.

---

## 9. Scale milestones

| Milestone | Action |
|---|---|
| 100 licenses | Review Groq/Gemini free quotas — may need paid tier |
| 500 licenses | Upgrade Railway to Pro plan ($20/mo) for more RAM |
| 1000 licenses | Separate `worker` service (Celery) from `api` |
| 5000 licenses | Dedicated Postgres (Neon Scale or self-host) + 2x app workers |

---

## 10. Version bumps + rollback

### Bump pi-backend version
```bash
# In pyproject.toml + app/__init__.py
__version__ = "0.2.0"

# Commit + push — Railway auto-deploys
git commit -am "release 0.2.0"
git push

# Watch rollout in Railway dashboard
```

### Rollback
Railway → Deployments → (previous successful deploy) → **Redeploy**.

### Plugin rollback
Upload older ZIP to `/admin/releases` → set `is_yanked=True` on bad version → customers get prev stable version on next update check.

---

## Troubleshooting

### "All providers failed" for every AI call
- Check `PI_AI_KEY_*` env vars in Railway (must match `ai_providers.slug` mapping).
- Open `/admin/providers` → toggle all to enabled.
- Check each provider's dashboard for quota exhaustion.

### Stripe webhook not crediting wallets
- Check `STRIPE_WEBHOOK_SECRET` matches Stripe dashboard's signing secret.
- Check Stripe events log → find `checkout.session.completed` → response body should have `"credited": <tokens>`.

### Migrations fail on first deploy
- Make sure `DATABASE_URL` uses `postgresql+asyncpg://` prefix (not just `postgresql://`).
- Drop + recreate: Railway Postgres → Settings → Reset DB → `railway up` again.

### Admin login returns 401 on correct password
- Verify admin user was created with `--name "..."` (not blank) and `is_admin=True`.
- Check JWT secret matches between app restarts: redeploying rotates nothing unless you explicitly change env var.

### Cost getting out of control
- Check `/admin/usage` margin per plugin.
- If Claude/GPT-4 fallback fires too often, set `is_enabled=false` on those providers (forces free-only).

---

## Cost estimate @ 100 paying customers

| Line item | $/month |
|---|---|
| Railway Pro ($5 credit) | $5 |
| Postgres + Redis plugins | $5 |
| Vercel Hobby (free up to 100GB-h) | $0 |
| Domain renewals (prorated) | $2 |
| Sentry Developer | $0 (free tier) |
| **Infrastructure total** | **~$12/mo** |
| | |
| AI upstream cost (if 10% fallback to paid) | ~$20/mo |
| Stripe fees (3% of revenue) | ~$30/mo if $1k revenue |
| **Variable cost** | **~$50/mo** |

**Revenue @ 100 paying:** 100 × $10/mo avg token spend = **$1,000/mo** → Gross margin ≈ **94%**.
