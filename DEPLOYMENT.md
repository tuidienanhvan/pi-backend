# Deployment

Pi Ecosystem runs on **3 separate platforms** — backend, database, cache each on different providers. This file documents the topology so a new contributor (or a future agent picking up a task) can answer "where does X actually run?" without digging through env files or chat history.

## Topology at a glance

```
┌─────────────────────────────────────────────────────────────┐
│  Customer WordPress site                                     │
│    └── plugins/pi-api  ──── iframe ────┐                    │
│                                          │                   │
└──────────────────────────────────────────┼───────────────────┘
                                           │
                                           ▼
                            ┌─────────────────────────────┐
                            │  Vercel: pi-dashboard-webapp│
                            │  (React SPA — app.pi-...)   │
                            └──────────────┬──────────────┘
                                           │ REST + WS
                                           ▼
                            ┌─────────────────────────────┐
                            │  Railway: pi-backend         │
                            │  (FastAPI · Docker · /health)│
                            └────┬────────────────────┬───┘
                                 │                    │
                                 ▼                    ▼
                       ┌──────────────────┐  ┌──────────────────┐
                       │  Neon            │  │  Upstash         │
                       │  Postgres (TLS)  │  │  Redis (TLS)     │
                       └──────────────────┘  └──────────────────┘
```

`pi-store-webapp` (separate Vercel project) is the storefront where customers buy plugins/themes — it talks to `pi-backend` via the same REST API.

## Service-by-service

### 1. `pi-backend` → Railway

- **Config**: [railway.toml](./railway.toml) — Docker builder, healthcheck `/health` (300s timeout for first-deploy alembic migrations), start cmd `bash scripts/start.sh`.
- **Image**: built from [Dockerfile](./Dockerfile) (multi-stage; python:3.12-slim base; non-root user `pi`).
- **Runtime**: gunicorn + uvicorn workers (`WEB_CONCURRENCY=2` default).
- **Deploy**: `railway up` from this directory.
- **Env vars**: set in the Railway dashboard (never committed). Required: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `APP_SECRET_KEY`, `CRON_SECRET`, `APP_CORS_ORIGINS`, `PI_AI_NEW_ROUTING_ENABLED`. Full list in [.env.example](./.env.example).
- **Logs**: Railway dashboard → Logs tab.

### 2. Postgres → Neon

- **Hostname pattern**: `*.neon.tech`
- **Connection**: via `DATABASE_URL` env var on Railway, e.g. `postgresql+asyncpg://USER:PASS@HOST.neon.tech/DBNAME`.
- **TLS**: forced on automatically by [app/core/db.py:43](./app/core/db.py) — recognizes `neon.tech`, `supabase.co`, `railway.app`, `cockroachlabs.cloud` hosts and sets `ssl=require`.
- **Migrations**: alembic. Run on every Railway deploy via `scripts/start.sh` before uvicorn boots (12 migrations as of 2026-05).
- **Manage**: Neon Console — branches, SQL editor, connection strings, point-in-time restore.

### 3. Redis → Upstash

- **Free tier**: 500k commands/month · 256 MB storage · 50 GB bandwidth · TLS enabled · AWS Oregon (us-west-2).
- **Database name**: `pi`
- **Hostname pattern**: `*.upstash.io` (e.g. `polite-squid-102521.upstash.io:6379`).
- **Connection**: via `REDIS_URL`, plus `CELERY_BROKER_URL` (DB 1) and `CELERY_RESULT_BACKEND` (DB 2).
- **Note**: Upstash treats each logical DB as a separate connection — make sure the broker / result backend URLs include the right DB index.
- **Manage**: [Upstash Console](https://console.upstash.com) — CLI, data browser, monitor, backups, ACL.

### 4. `pi-dashboard-webapp` → Vercel

- **Config**: [`pi-dashboard-webapp/vercel.json`](../pi-dashboard-webapp/vercel.json) — single SPA rewrite (`/(.*)` → `/index.html`).
- **Build output**: `dist/` (post T-005 — was previously `../plugins/pi-dashboard/assets/app/`; pi-dashboard plugin shell removed).
- **Runtime URL**: `app.pi-ecosystem.com` (the iframe target in `pi-api` plugin).
- **Embedded into**: WordPress admin via `plugins/pi-api/`'s iframe.

### 5. `pi-store-webapp` → Vercel

- **Config**: [`pi-store-webapp/vercel.json`](../pi-store-webapp/vercel.json) — filesystem handler + SPA fallback. Also has `/api/*` routes (Vercel Serverless Functions).
- **Build output**: `build/`.
- **Runtime URL**: storefront for plugin/theme sales.

## Local development

Local dev uses `docker-compose.yml` (Postgres 18 + Redis 7 + api + worker) — does NOT use Neon/Upstash. Production env vars are completely separate. See [.env.example](./.env.example) for full local config.

```bash
docker compose up -d        # postgres + redis + api + worker
docker compose logs -f api  # tail
```

## What this stack costs (rough)

- **Railway**: usage-based (CPU/RAM/network) — free trial credits then pay-as-you-go.
- **Neon**: free tier covers small projects (0.5 GB storage, autosuspend); paid tiers scale.
- **Upstash**: free tier as above; cap will trigger if traffic spikes.
- **Vercel**: free tier covers hobby projects; SPA + minimal serverless usually fits.

## Production toggles to verify

Before going live, ensure these mock/dev-mode switches are disabled:

### Mock modes that MUST be disabled in production

| Env var / Config | File / Location | Purpose | Production setting |
|---|---|---|---|
| `VITE_MOCK_AUTH` | pi-store-webapp/.env.production | Bypass real auth — accepts any email | **Must be unset or `0`** |
| `PI_API_MOCK_MODE` | plugins/pi-api — wp-config.php or .env | Mock all BackendClient responses | **Must be `false` or unset** |
| `VITE_USE_MOCK` | pi-dashboard-webapp/.env.production | Use mock API responses | **Must be unset** |
| `VITE_DEMO_MODE` | pi-store-webapp/.env | Simulate Stripe checkout flow | **Must be unset** |

### Feature flags

| Env var | File / Location | Purpose | Production setting |
|---|---|---|---|
| `PI_AI_NEW_ROUTING_ENABLED` | Railway env → pi-backend | Enable per-package AI provider routing | **Set `true` once routing policies configured** |
| `GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON` | Railway env → pi-backend | Path or inline JSON for Google service account | **Set to service account JSON when ready** |

### Endpoints with dev-only behavior

- `POST /v1/billing/subscribe/simulate-success` — Development-only Stripe simulation. **Guarded**: returns 404 in production (`app_env == "production"`).
- `POST /v1/admin/licenses` — Creates real license keys. No dev guard needed (requires admin JWT).

### Checklist

1. [ ] Set `APP_ENV=production` on Railway
2. [ ] Unset `PI_API_MOCK_MODE` in wp-config.php
3. [ ] Unset `VITE_MOCK_AUTH` and `VITE_DEMO_MODE` in Vercel env
4. [ ] Unset `VITE_USE_MOCK` in Vercel env for pi-dashboard
5. [ ] Configure `GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON` if using instant indexing
6. [ ] Set `PI_AI_NEW_ROUTING_ENABLED=true` after configuring provider routing policies
7. [ ] Verify `/health` endpoint returns OK on Railway

## Future considerations

- Pi backend cold start: alembic + uvicorn ~15-25s on first deploy after schema changes; healthcheck timeout set to 300s.
- If pi-backend ever needs >1 instance, Postgres pool sizing (`DATABASE_POOL_SIZE=10`) per-instance × workers matters — Neon free tier has connection limits.
- Upstash 500k commands/month is enough for a few thousand users at chatbot-cache levels; revisit if AI request volume spikes.
