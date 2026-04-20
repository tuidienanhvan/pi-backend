# Deploy to Railway — step by step

Railway is the easiest way to get Pi Backend online. Target: **under 15 minutes from zero to live API**.

## Prerequisites

- GitHub account (Railway auto-deploys on push)
- Railway account (https://railway.app — free tier gives $5/month credit)
- Anthropic API key (https://console.anthropic.com)

## Step 1 — Push code to GitHub

```bash
cd pi-backend
git init
git add .
git commit -m "initial commit"
git remote add origin git@github.com:yourorg/pi-backend.git
git push -u origin main
```

## Step 2 — Create Railway project

1. Go to https://railway.app/new
2. Click **"Deploy from GitHub repo"** → pick `pi-backend`
3. Railway auto-detects `Dockerfile` and starts building

Wait for first build — it will fail (no DB yet). That's fine.

## Step 3 — Add PostgreSQL

1. In the project, click **"+ New"** → **Database** → **Add PostgreSQL**
2. Open the Postgres service → **Variables** tab → copy `DATABASE_URL`
3. Open the `pi-backend` service → **Variables** tab → paste as `DATABASE_URL`
4. **Important:** change the scheme from `postgresql://` to `postgresql+asyncpg://`

Example:
```
DATABASE_URL=postgresql+asyncpg://postgres:xxx@autorack.proxy.rlwy.net:12345/railway
```

## Step 4 — Add Redis

1. **"+ New"** → **Database** → **Add Redis**
2. Copy `REDIS_URL` → set on `pi-backend` service
3. Also set:
   ```
   CELERY_BROKER_URL=${{Redis.REDIS_URL}}
   CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
   ```
   (Railway variable references work across services.)

## Step 5 — Set secrets

On the `pi-backend` service → **Variables** → add:

```
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=<run: python -c "import secrets;print(secrets.token_hex(32))">
JWT_SECRET=<same command, different output>
APP_BASE_URL=https://${{RAILWAY_STATIC_URL}}
APP_CORS_ORIGINS=https://your-wp-site.com,https://another-site.com

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929

LICENSE_KEY_PREFIX=pi_
RATE_LIMIT_FREE_PER_MONTH=20
RATE_LIMIT_PRO_PER_MONTH=500
RATE_LIMIT_AGENCY_PER_MONTH=5000

LOG_LEVEL=INFO
```

## Step 6 — Redeploy

Click **Deploy** (or push a new commit). Railway runs:
```
alembic upgrade head && gunicorn app.main:app ...
```

Migrations create all tables on first run.

## Step 7 — Verify

```bash
curl https://your-app.up.railway.app/health
# → {"status":"ok"}

curl https://your-app.up.railway.app/ready
# → {"status":"ok","database":"ok","redis":"ok"}
```

## Step 8 — Custom domain

1. In Railway → **Settings** → **Domains** → **Custom Domain**
2. Enter `api.piwebagency.com`
3. Add CNAME in your DNS: `api → <railway-provided-target>`
4. Wait 5 min for SSL cert

## Step 9 — Create first real license

Open a Railway shell (or use `railway run`):

```bash
railway run python -m scripts.create_license \
    --plugin pi-seo-pro \
    --email admin@piwebagency.com \
    --tier agency \
    --max-sites 100 \
    --expires-days 36500

# Copy the key — this is your own "admin" license for testing
```

## Scaling

- **1 worker, 512MB RAM** handles ~50 req/sec (most endpoints are I/O to Claude).
- If you hit limits:
  - Bump `WEB_CONCURRENCY` env var (more gunicorn workers)
  - Upgrade to Railway Pro plan ($20/month) for dedicated resources
  - Add a separate `worker` service for Celery (same Dockerfile, different start cmd)

## Troubleshooting

### `"psycopg2 not installed"`
You forgot the `+asyncpg` prefix on `DATABASE_URL`.

### Migrations fail with "relation already exists"
Someone ran migrations twice. Check `alembic_version` table:
```sql
SELECT * FROM alembic_version;
```

### Claude calls timeout
Increase `gunicorn --timeout` in `railway.toml` (default 60s).

### Can't find the app after custom domain
DNS takes up to 1h to propagate. Check with:
```bash
dig api.piwebagency.com
```

---

## Cost estimate

| Scale | Resources | $/mo |
|---|---|---|
| 0-50 sites pinging daily | 1 service + Postgres + Redis (Hobby) | **$5** |
| 50-500 sites, 1k AI calls/day | Pro plan + more RAM | **$25** |
| 500+ sites, 10k+ AI calls/day | Upgrade Pro + dedicated worker + Postgres Pro | **$75+** |

Most cost will be Anthropic API calls, not Railway.
