# Quick start — first 10 minutes

**Goal:** spin up the stack locally, create a license, call `/v1/seo-bot/generate`.

## Prerequisites

- Docker Desktop (Windows/Mac) or docker + docker-compose (Linux)
- Anthropic API key (https://console.anthropic.com — new account gets $5 credit)

## 1. Configure secrets

```bash
cd pi-backend
cp .env.example .env
```

Edit `.env`:
```
APP_SECRET_KEY=<paste 64 random chars>
JWT_SECRET=<paste different 64 random chars>
ANTHROPIC_API_KEY=sk-ant-your-real-key
```

Generate secrets quickly:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Or on Windows PowerShell:
# -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | % {[char]$_})
```

## 2. Start the stack

```bash
docker compose up -d
```

First run takes ~2 min (pulls Postgres, Redis, builds app). You'll see:
```
[+] Running 5/5
 ✔ Network pi-backend_default       Created
 ✔ Container pi-backend-postgres-1  Healthy
 ✔ Container pi-backend-redis-1     Healthy
 ✔ Container pi-backend-api-1       Started
 ✔ Container pi-backend-worker-1    Started
```

## 3. Verify it's up

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/ready
# {"status":"ok","database":"ok","redis":"ok"}
```

**Open the API docs:** http://localhost:8000/docs

You should see Swagger UI with all endpoints.

## 4. Create your first license

```bash
docker compose exec api python -m scripts.create_license \
    --plugin pi-seo-pro \
    --email test@example.com \
    --tier pro \
    --max-sites 3
```

Output:
```
────────────────────────────────────────────
  License created: id=1
  Key:     pi_a1b2c3d4e5f6789012345678901234ab
  Plugin:  pi-seo-pro
  Email:   test@example.com
  Tier:    pro
  Sites:   max 3
  Expires: 2027-04-17 ...
────────────────────────────────────────────
```

**Copy that key** — you need it for the next step.

## 5. Activate a site

```bash
KEY="pi_a1b2c3d4e5f6789012345678901234ab"   # your key

curl -X POST http://localhost:8000/v1/license/activate \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "site_url": "https://demo.local",
    "plugin_version": "1.3.0",
    "wp_version": "6.5",
    "php_version": "8.3"
  }'
```

Response:
```json
{
  "success": true,
  "site_id": 1,
  "activated_sites": 1,
  "max_sites": 3,
  "message": "Activated"
}
```

## 6. Call SEO Bot (the expensive one)

```bash
curl -X POST http://localhost:8000/v1/seo-bot/generate \
  -H "Authorization: Bearer $KEY" \
  -H "X-Pi-Site: demo.local" \
  -H "Content-Type: application/json" \
  -d '{
    "site_url": "https://demo.local",
    "post_id": 42,
    "post_title": "Hướng dẫn SEO WordPress cơ bản cho người mới",
    "focus_keyword": "SEO WordPress",
    "excerpt": "Bài viết này sẽ chỉ bạn cách tối ưu SEO trên WordPress từ A đến Z.",
    "content_snippet": "WordPress là nền tảng blog phổ biến nhất thế giới...",
    "tone": "professional",
    "language": "vi",
    "variants": 2
  }'
```

Response (takes ~3-5s):
```json
{
  "success": true,
  "variants": [
    {
      "title": "SEO WordPress Cho Người Mới: Hướng Dẫn Toàn Diện 2026",
      "description": "Học cách tối ưu SEO WordPress từ cơ bản đến nâng cao...",
      "og_image_prompt": "Modern laptop with WordPress dashboard, Vietnamese text overlay",
      "slug_suggestion": "seo-wordpress-cho-nguoi-moi"
    },
    {
      "title": "Cẩm Nang SEO WordPress Từ A-Z Cho Người Mới Bắt Đầu",
      "description": "Khám phá các bước SEO WordPress hiệu quả...",
      "og_image_prompt": "...",
      "slug_suggestion": "cam-nang-seo-wordpress"
    }
  ],
  "tokens_used": 742,
  "model": "claude-sonnet-4-5-20250929"
}
```

## 7. Check stats

```bash
curl http://localhost:8000/v1/license/stats \
  -H "Authorization: Bearer $KEY"
```

```json
{
  "key_prefix": "pi_a1b2c3d4e5...",
  "tier": "pro",
  "activated_sites": 1,
  "max_sites": 3,
  "usage_this_month": 1,
  "quota_this_month": 500,
  ...
}
```

## 8. Run tests (optional)

```bash
docker compose exec api pytest -v
```

Tests that need no network/DB (`test_prompts.py`, `test_scorer.py`, `test_license_service.py`) pass instantly.

## 9. Stop everything

```bash
docker compose down
# Or keep data:
# docker compose stop
```

## Next steps

- **Integrate with Pi SEO plugin:** see `docs/WP_PLUGIN_INTEGRATION.md`
- **Deploy to Railway:** see `docs/DEPLOY_RAILWAY.md`
- **Customize prompts:** edit `app/prompts/seo_bot.py` → restart API

## Common gotchas

### Port 5432 already in use
You have another Postgres running. Edit `docker-compose.yml`:
```yaml
postgres:
  ports:
    - "5433:5432"  # use 5433 externally
```
And update `.env`:
```
DATABASE_URL=postgresql+asyncpg://pi:pi@localhost:5433/pi_backend
```
(Inside docker network it still uses 5432, only host port differs.)

### "relation does not exist" on first request
Migrations didn't run. Manual:
```bash
docker compose exec api alembic upgrade head
```

### Claude returns "Invalid API key"
Your `ANTHROPIC_API_KEY` is wrong or expired. Get a new one at https://console.anthropic.com.

### Swagger UI shows "Failed to fetch" on every call
Browser CORS — not applicable if you use the "Try it out" button in Swagger. If calling from a real JS app, add that origin to `APP_CORS_ORIGINS`.
