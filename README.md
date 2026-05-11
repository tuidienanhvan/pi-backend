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
│   └── pi_api/                    # 🎯 Pi Unified API (SEO, Chatbot, Leads, etc.)
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
| `pi-api` | `app/pi_api/` | **Unified Plugin (Platform)** |
| — (backend-only) | `app/pi_ai_cloud/` | **3 Tiers: Free, Pro, Max** |

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
/v1/ai/providers                                           Transparency list

/v1/pi/v1/*                                                Unified Plugin Endpoints (SEO, Chat, Leads, etc.)
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

## Admin DB Access (SQLAdmin)

Browse: `http://localhost:8000/admin/db`

This is a direct database admin UI for internal development and debugging. Do not expose it to the public internet in production; put it behind VPN/internal network controls.

Login:
- Username: any value
- Password: paste a user JWT with `is_admin=true`

Get an admin JWT:

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pi.local","password":"..."}' | jq -r .access_token
```

Set a strong session secret before running:

```bash
openssl rand -hex 32
# then set SQLADMIN_SESSION_SECRET=<generated-value>
```

Registered tables include tenants, tenant tokens, tenant token transactions, licenses, sites, users, AI wallets, AI ledgers, AI providers, AI usage, usage logs, and admin audit logs. Secret fields such as password hashes are excluded from list/forms.

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
