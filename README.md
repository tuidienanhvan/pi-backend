# Pi Backend API

Backend services for the Pi WordPress ecosystem — organised **by plugin**. Each Pi plugin that needs a server-side counterpart has its own folder under `app/`.

**Stack:** Python 3.12 · FastAPI · PostgreSQL 16 · Redis 7 · Celery · Docker

**Primary revenue:** [Pi AI Cloud](docs/PI_AI_CLOUD.md) — token-based AI gateway (85% gross margin on free-provider arbitrage).

---

## ⚠️ About this location (`wp-content/pi-backend/`)

This folder lives inside `wp-content/` for developer convenience — one IDE workspace edits both WP plugins and the Python API.

**It is NOT served by WordPress.** The backend runs as a standalone Docker container (locally) or Railway service (production). WordPress never loads any file from here.

**Safety rails included:**
- `.htaccess` denies all HTTP access (Apache)
- `index.php` returns 403 (fallback for any PHP router)
- `.gitignore` excludes `.env`, `.venv`, `data/`, logs

**Do NOT include this folder in your WordPress deploy ZIP.**

```bash
zip -r wp-site.zip wp-content -x "wp-content/pi-backend/*"
```

For **nginx hosts**, add to server block:
```nginx
location ^~ /wp-content/pi-backend/ { return 403; }
```

---

## Project structure — plugin-first

```
pi-backend/
├── app/
│   ├── main.py                    # FastAPI entrypoint + router registration
│   ├── models.py                  # Central ORM registry (for Alembic)
│   ├── worker.py                  # Celery app
│   │
│   ├── core/                      # 🔧 Shared infrastructure
│   │   ├── base.py                #    SQLAlchemy Base + TimestampMixin
│   │   ├── config.py              #    Pydantic Settings (env-backed)
│   │   ├── db.py                  #    Async SQLAlchemy engine + session
│   │   ├── deps.py                #    FastAPI deps (auth, rate limit)
│   │   ├── exceptions.py          #    Custom exceptions
│   │   ├── logging_conf.py
│   │   ├── middleware.py
│   │   ├── redis_client.py
│   │   └── schemas.py             #    Common DTOs
│   │
│   ├── shared/                    # 🌐 Used by ALL Pi plugins
│   │   ├── claude.py              #    Direct Anthropic wrapper (legacy)
│   │   ├── rate_limit.py          #    Redis sliding window
│   │   ├── tasks.py               #    Celery registry
│   │   ├── usage.py               #    UsageLog model
│   │   ├── health.py              #    /health /ready
│   │   ├── license/               #    License + Site domain
│   │   ├── updates/               #    Plugin release server
│   │   └── telemetry/             #    Plugin heartbeat
│   │
│   ├── pi_ai_cloud/               # 💰 Pi AI Cloud — TOKEN GATEWAY (primary revenue)
│   │   ├── models.py              #    TokenWallet, TokenLedger, AiProvider, AiUsage
│   │   ├── schemas.py
│   │   ├── providers/             #    Upstream adapters
│   │   │   ├── base.py
│   │   │   └── openai_compat.py   #    Covers Groq, Mistral, Together, …
│   │   ├── services/
│   │   │   ├── wallet.py          #    Balance + ledger
│   │   │   ├── router.py          #    Provider selection + circuit breaker
│   │   │   ├── completion.py      #    Orchestrator
│   │   │   └── billing.py         #    Stripe Checkout + webhook
│   │   └── routers/
│   │       ├── complete.py        #    POST /v1/ai/complete
│   │       └── tokens.py          #    /wallet, /ledger, /topup/*, /providers
│   │
│   ├── pi_seo/                    # 🎯 Pi SEO Pro
│   │   ├── schemas.py             #    Merged DTOs (bot + audit + schema)
│   │   ├── prompts.py             #    🔒 SEO Bot prompts
│   │   ├── data/
│   │   │   ├── audit_weights.py   #    🔒 100-point rules
│   │   │   └── schema_templates.py #   🔒 Curated JSON-LD library
│   │   ├── services/
│   │   │   ├── seo_bot.py
│   │   │   ├── html_analyzer.py
│   │   │   └── scorer.py
│   │   └── routers/
│   │       ├── seo_bot.py         #    /v1/seo/bot/*
│   │       ├── audit.py           #    /v1/seo/audit/*
│   │       └── schema.py          #    /v1/seo/schema/*
│   │
│   ├── pi_chatbot/                # 💬 Pi Chatbot Pro (scaffold)
│   ├── pi_leads/                  # 📋 Pi Leads Pro (scaffold)
│   ├── pi_analytics/              # 📊 Pi Analytics Pro (scaffold)
│   ├── pi_performance/            # ⚡ Pi Performance Pro (scaffold)
│   └── pi_dashboard/              # 🏠 Pi Dashboard (scaffold)
│
├── migrations/
│   └── versions/
│       ├── 001_initial.py         # licenses, sites, usage_logs, plugin_releases
│       └── 002_pi_ai_cloud.py     # ai_token_wallets, ledger, providers, usage
│
├── scripts/
│   ├── create_license.py
│   ├── upload_release.py
│   └── seed_ai_providers.py       # Seed Groq, Gemini, Mistral, Cohere, Together
│
├── tests/                         # pytest
├── docs/
│   ├── QUICKSTART.md              # 10-min local setup
│   ├── PI_AI_CLOUD.md             # 💰 Token economy + margins
│   ├── WP_PLUGIN_INTEGRATION.md   # PiBackendClient.php
│   └── DEPLOY_RAILWAY.md          # 15-min prod deploy
│
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── alembic.ini
├── railway.toml
└── Makefile
```

---

## Mapping: WP plugin → Backend module

| WordPress plugin | Folder in pi-backend | Revenue tier |
|---|---|---|
| `pi-dashboard` | `app/pi_dashboard/` | FREE (platform) |
| `pi-ai-provider` | (backbone, no backend module) | FREE (internal) |
| `pi-seo` | `app/pi_seo/` | **Pro $49-99/yr** |
| `pi-chatbot` | `app/pi_chatbot/` | **Pro $29/mo SaaS** |
| `pi-leads` | `app/pi_leads/` | **Pro $39-79/yr** |
| `pi-analytics` | `app/pi_analytics/` | **Pro $29-49/yr** |
| `pi-performance` | `app/pi_performance/` | **Pro $29-49/yr** |
| — (backend-only) | `app/pi_ai_cloud/` | **💰 Tokens $10/100k** ← PRIMARY |

---

## URL prefix convention

```
/health                                                    Liveness probe
/ready                                                     Readiness (DB + Redis)

/v1/license/{verify,activate,deactivate,stats}             Shared license
/v1/updates/{check/:plugin, download/:plugin/:ver}         Plugin update server
/v1/telemetry/ping                                         Shared heartbeat

/v1/ai/complete                                            💰 Main paid endpoint
/v1/ai/wallet                                              Customer balance
/v1/ai/ledger                                              Transaction history
/v1/ai/topup/{checkout, packs}                             Stripe integration
/v1/ai/stripe/webhook                                      Event handler
/v1/ai/providers                                           Transparency list

/v1/seo/bot/{generate, bulk, status/:id}                   Pi SEO Pro — AI
/v1/seo/audit/{run, content}                               Pi SEO Pro — scoring
/v1/seo/schema/{templates, templates/:id}                  Pi SEO Pro — library

/v1/chatbot/*                                              Scaffolded (Phase 2)
/v1/leads/*                                                Scaffolded (Phase 2)
/v1/analytics/*                                            Scaffolded (Phase 2)
/v1/perf/*                                                 Scaffolded (Phase 2)
/v1/dashboard/*                                            Scaffolded (Phase 2)
```

---

## Quick start

```bash
cd pi-backend
cp .env.example .env
# Edit .env — APP_SECRET_KEY, JWT_SECRET, STRIPE_SECRET_KEY, PI_AI_KEY_*

docker compose up -d
# → postgres + redis + api (runs alembic upgrade) + worker

docker compose exec api python -m scripts.seed_ai_providers
# Seeds 7 providers (5 free + 2 paid fallback)

docker compose exec api python -m scripts.create_license \
    --plugin pi-seo-pro --email you@test.com --tier pro
# → returns license key pi_abc...

# Wallet auto-created with 1,000 free tokens on first call:
curl http://localhost:8000/v1/ai/wallet \
    -H "Authorization: Bearer pi_abc..."
```

See `docs/QUICKSTART.md` for full walkthrough.

---

## Architecture principles

1. **One folder per plugin** — easy to find, add, remove
2. **Shared code in `shared/`** — license, updates, telemetry used by every plugin
3. **Infrastructure in `core/`** — swap DB/Redis/AI without touching plugin code
4. **`app/models.py` is the ORM registry** — Alembic autogenerate sees every table
5. **Router prefix = plugin slug** — URLs tell you which module owns the code
6. **Prompts + weights are IP** — never copy to `shared/` or client code

---

## Adding a new plugin to the backend

1. Create `app/pi_newplugin/`:
   ```
   app/pi_newplugin/
   ├── __init__.py      # Docstring — revenue tier + purpose
   ├── schemas.py       # Pydantic DTOs
   ├── models.py        # SQLAlchemy (if needed)
   ├── services/        # Business logic
   └── routers/
       └── main.py      # Endpoints
   ```

2. Register in `app/main.py`:
   ```python
   from app.pi_newplugin.routers.main import router as newplugin_router
   app.include_router(newplugin_router, prefix="/v1/newplugin", tags=["pi-newplugin"])
   ```

3. If new models: import them in `app/models.py` so Alembic sees them.

4. Generate migration:
   ```bash
   docker compose exec api alembic revision --autogenerate -m "add pi_newplugin"
   ```

5. Update this README's structure section.

---

## Docs

- **`docs/QUICKSTART.md`** — 10-minute local setup
- **`docs/PI_AI_CLOUD.md`** — 💰 Token economy, margin, routing, Stripe flow
- **`docs/WP_PLUGIN_INTEGRATION.md`** — Drop-in `PiBackendClient.php`
- **`docs/DEPLOY_RAILWAY.md`** — Deploy to prod in 15 min

---

## License

Proprietary — Pi Ecosystem. Not for redistribution.
