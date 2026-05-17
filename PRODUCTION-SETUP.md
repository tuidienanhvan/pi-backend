# Production Setup Runbook

Trạng thái Pi backend production tính đến **2026-05-17**, sau session bootstrap đầu tiên. File này là single source of truth cho "đã làm gì rồi" + "còn lại làm gì" để đưa Pi Ecosystem online.

> **Khi nào cần đọc**: lúc onboard người mới vào team, troubleshoot khi prod xuống, hoặc tiếp tục bootstrap sau khi pause. Bổ sung cho [DEPLOYMENT.md](./DEPLOYMENT.md) (topology) — file này focus vào **state + checklist**.

---

## 1. ✅ Đã có (Done)

### 1.1 Infrastructure

| Service | Platform | Status |
|---|---|---|
| Backend FastAPI | Railway · `pi-backend.up.railway.app` | 🟢 Online, healthcheck `/health` passing |
| Postgres | Neon (`*.neon.tech`, us-west-2, pooler) | 🟢 Schema created (10 migrations applied) |
| Redis + Celery broker/result | Upstash (`polite-squid-102521.upstash.io`, AWS Oregon, TLS) | 🟢 Connected, free tier (500k cmds/month) |
| Dashboard webapp | Vercel · `pi-dashboard-wordpress.vercel.app` | 🟢 Deployed |
| Store webapp | Vercel · `pi-store-webapp.vercel.app` | 🟢 Deployed |

### 1.2 Railway env vars (13 vars set)

`APP_ENV=production` · `APP_DEBUG=false` · `APP_SECRET_KEY` · `APP_BASE_URL=https://pi-backend.up.railway.app` · `APP_CORS_ORIGINS` (dashboard + store Vercel URLs) · `DATABASE_URL` (Neon pooler with sslmode+channel_binding) · `REDIS_URL` · `CELERY_BROKER_URL` (Upstash DB 1) · `CELERY_RESULT_BACKEND` (Upstash DB 2) · `JWT_SECRET` · `PI_AI_NEW_ROUTING_ENABLED=true` · `CRON_SECRET` · `GOOGLE_PSI_API_KEY`.

→ Defaults trong [`app/core/config.py`](./app/core/config.py) phủ phần còn lại (pool sizes, JWT algorithm, rate limits, log level, etc.).

### 1.3 Database seed

| Table | Rows | How seeded |
|---|---|---|
| `users` | **1** — admin `9.13.tuanhvan2018@gmail.com` (Tu Anh Van) — `is_admin=t`, `is_active=t`, `is_verified=t` | `scripts/create_admin.py` (manually) |
| `ai_providers` | **24** providers across free + paid tiers | `scripts/seed_ai_providers.py` via `railway run` |
| `ai_packages` | **3** — `package/free`, `package/pro`, `package/max` | Same script |
| `licenses` | **1** — Pro license cho admin email, plugin=`pi-api` | `scripts/seed_pro_licenses.py --email 9.13.tuanhvan2018@gmail.com` |
| `ai_provider_keys` (pool) | **0** — chưa add real keys | Manual via admin UI hoặc env vars (xem §2.2) |

### 1.4 Code changes (this session)

- **T-20260517-005** ARCHIVED — Removed `plugins/pi-dashboard/` shell plugin + hardened pi-api iframe (15 security/bug fixes including mock JWT bypass, dead AJAX path, missing CSP, hardcoded CSS, etc.)
- **T-20260517-008** ARCHIVED — Switched `PI_API_BACKEND_URL` từ `app.pi-ecosystem.com` (chưa có domain) → `pi-dashboard-wordpress.vercel.app` + bump plugin version `1.0.0 → 1.0.1`
- **T-20260517-006** DRAFTED (HOLD) — JWT URL→postMessage handshake migration (cần dispatch khi sẵn sàng)
- **T-20260517-010** Phase B done — Tier spec single source of truth in `app/saas/tiers.py` + `GET /v1/tiers/spec` endpoint live. See [TIER-MATRIX.md](./TIER-MATRIX.md) for canonical reference. Phase C-E (consumer sync — pi-api, dashboard, store) queued.

### 1.6 Tier matrix (canonical)

| | Free | Pro | Max | Enterprise |
|---|---|---|---|---|
| Price USD/mo | $0 | $29 | $99 | Custom |
| Monthly tokens | 50,000 | 1,000,000 | 3,000,000 | Unlimited |
| Max sites | 1 | 3 | 10 | Unlimited |
| Features | 1 | 4 | 7 | All |

Full spec + edge cases: [TIER-MATRIX.md](./TIER-MATRIX.md).
Live endpoint: `GET https://pi-backend.up.railway.app/v1/tiers/spec` (cache 1h).

### 1.5 CLI tools installed

- Railway CLI 4.58.0 · logged in as `9.13.tuanhvan2018@gmail.com` · linked to project `independent-integrity / production / pi-backend`
- Neon CLI (`neonctl`) 2.22.0 · chưa login (chạy `neonctl auth` khi cần branch ops)
- Vercel CLI 54.1.0 · chưa login (chạy `vercel login` khi cần CLI ops)

---

## 2. 🔄 Còn lại làm thủ công (Manual TODO)

### 2.1 ⚠️ CRITICAL — Rotate 3 secrets

Anh đã paste 3 secrets vào chat → cần rotate sau khi setup xong:

```bash
# Generate new secrets
python -c "import secrets; print('APP_SECRET_KEY=' + secrets.token_hex(32))"
python -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('CRON_SECRET=' + secrets.token_hex(32))"
```

Update qua Railway dashboard → Variables tab → paste new values. Sau khi save, Railway tự redeploy (mất ~30s). JWT rotation sẽ invalidate session hiện tại — admin phải đăng nhập lại.

Database/Redis password rotation phức tạp hơn (cần coordination với Neon/Upstash console) — làm sau khi stable.

### 2.2 ⚠️ HIGH — Add real AI API keys

Pool đang trống → mọi request đến `/v1/ai/complete` sẽ fail. Lấy free keys từ:

| Provider | Lấy ở đâu | Free quota notable |
|---|---|---|
| **Groq** ⭐ | [console.groq.com](https://console.groq.com) | ~14M tokens/day per key |
| **Gemini 2.0 Flash** ⭐ | [aistudio.google.com](https://aistudio.google.com) | 3M tokens/day per key |
| **Cerebras** ⭐ | [cerebras.ai/cloud](https://cerebras.ai/cloud) | 1M tokens/day, very fast |
| **Mistral** | [console.mistral.ai](https://console.mistral.ai) | Free tier |
| **Cohere** | [dashboard.cohere.com](https://dashboard.cohere.com) | Free trial |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | Mix free + paid models |
| **SiliconFlow** | [siliconflow.cn](https://siliconflow.cn) | Free Qwen access |
| **GitHub Models** | [github.com/marketplace/models](https://github.com/marketplace/models) | Free with GitHub account |

**Add keys bằng 2 cách:**

**Cách A — qua admin UI** (recommended sau khi dashboard online):
1. Login Pi Dashboard tại `https://pi-dashboard-wordpress.vercel.app`
2. Vào `/admin/keys` (hoặc menu tương đương trong AiProviders feature)
3. Click "Add key" → chọn provider → paste API key
4. Test connection (button "Test")
5. Lặp lại cho ≥3 providers (Groq + Gemini + Cerebras tối thiểu)

**Cách B — qua Railway env vars** (alternative):
Thêm vào Railway Variables tab:
```
PI_AI_KEY_GROQ_LLAMA_70B_FREE=gsk_...
PI_AI_KEY_GEMINI_2_FLASH_FREE=AIzaSy...
PI_AI_KEY_CEREBRAS_LLAMA_FREE=csk_...
```
Sau đó chạy script sync env → DB (em chưa thấy script này — có thể cần tạo, hoặc Cách A đơn giản hơn).

### 2.3 Reallocate keys to admin's license

Pro license của admin có `keys allocated: 0` vì pool trống lúc tạo. Sau khi add keys (§2.2), chạy:

```bash
cd "C:/Users/Administrator/Local Sites/saigonhouse/app/public/wp-content/pi-backend"
railway run ".venv\Scripts\python.exe" -X utf8 -m scripts.seed_pro_licenses --email 9.13.tuanhvan2018@gmail.com
```

Script idempotent — license không bị tạo lại, chỉ retry allocation. Expect: `keys allocated: 2` (Groq + Gemini).

### 2.4 Smoke test pi-api plugin trên saigonhouse.local

License key lấy được từ seed output ở section §1.3 (lưu an toàn — KHÔNG commit).

1. WP admin `saigonhouse.local` → Plugins → activate `Pi API`
2. Pi API menu → License page → paste license key → Activate
3. Sau activate, menu **Pi Dashboard** xuất hiện
4. Click → iframe load từ `https://pi-dashboard-wordpress.vercel.app/?iframe=1&t=<JWT>`
5. **DevTools checks**:
   - Network tab → confirm iframe loads OK (HTTP 200)
   - Console → no CORS errors, no JS errors
   - Application/Storage → no leaked credentials
6. Test mid-session:
   - Wait > JWT TTL or trigger session-expired
   - Confirm refresh flow works (T-005 wired the `pi_api_refresh_jwt` AJAX handler)

### 2.5 (Optional) Setup custom domain sau khi mua

Khi mua `pi-ecosystem.com`:
1. DNS provider: CNAME `app` → `cname.vercel-dns.com`, CNAME `store` → `cname.vercel-dns.com`
2. Vercel CLI:
   ```bash
   vercel login
   cd pi-dashboard-webapp && vercel link    # chọn project
   vercel domains add app.pi-ecosystem.com
   cd ../pi-store-webapp && vercel link
   vercel domains add store.pi-ecosystem.com
   ```
3. Update Railway CORS:
   ```bash
   cd pi-backend
   railway variables --set "APP_CORS_ORIGINS=https://pi-dashboard-wordpress.vercel.app,https://pi-store-webapp.vercel.app,https://app.pi-ecosystem.com,https://store.pi-ecosystem.com"
   ```
4. Override `PI_API_BACKEND_URL` trên customer WP sites bằng wp-config.php:
   ```php
   define('PI_API_BACKEND_URL', 'https://app.pi-ecosystem.com');
   ```
   (constant trong pi-api plugin guarded bởi `if (!defined(...))` → wp-config override winning)

### 2.6 (Optional) Stripe billing

Khi enable monetization:
- Get keys từ [dashboard.stripe.com](https://dashboard.stripe.com) → Developers → API keys
- Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_MAX_PRICE_ID` trong Railway
- Configure webhook endpoint trên Stripe dashboard → URL: `https://pi-backend.up.railway.app/v1/billing/webhook`

### 2.7 (Optional) SMTP email

Khi cần gửi email (license activation, password reset):
- Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL=no-reply@pi-ecosystem.com`
- Provider gợi ý: Postmark, SendGrid, Resend, Amazon SES

### 2.8 (Optional) Sentry error monitoring

Set `SENTRY_DSN` trong Railway → backend tự log errors. Sentry free tier đủ cho early-stage prod.

---

## 3. 🩺 Verify queries (chạy trên Neon SQL Editor)

```sql
-- Provider count by tier
SELECT tier, COUNT(*) AS count
FROM ai_providers
GROUP BY tier
ORDER BY tier;
-- Expect: free ~21, paid 3

-- Top priority providers
SELECT slug, display_name, tier, priority, is_enabled, base_url
FROM ai_providers
ORDER BY priority
LIMIT 10;

-- Packages
SELECT slug, display_name, monthly_tokens, price_cents
FROM ai_packages;
-- Expect: 3 rows (free/pro/max)

-- Admin user
SELECT id, email, name, is_admin, is_active, is_verified
FROM users;
-- Expect: 1 row (Tu Anh Van, is_admin=t)

-- Licenses
SELECT l.id, l.email, l.plugin, l.tier, l.status, l.key
FROM licenses l
WHERE l.email = '9.13.tuanhvan2018@gmail.com';
-- Expect: 1 row (Pro license for pi-api)

-- Key pool (after manually adding via UI)
SELECT p.slug, COUNT(k.id) AS keys_total,
       SUM(CASE WHEN k.allocated_to IS NULL THEN 1 ELSE 0 END) AS available
FROM ai_providers p
LEFT JOIN ai_provider_keys k ON k.provider_id = p.id
GROUP BY p.slug
HAVING COUNT(k.id) > 0
ORDER BY keys_total DESC;
-- Expect: rows for each provider where you added keys

-- Recent audit log (admin actions)
SELECT id, actor_email, action, target_type, target_id, created_at
FROM audit_log
ORDER BY created_at DESC
LIMIT 20;
```

---

## 4. 🚨 Troubleshooting

| Triệu chứng | Check | Fix |
|---|---|---|
| `/health` 500 trên Railway | Railway logs → look for alembic / DB connection error | Verify `DATABASE_URL` env var; check Neon project not suspended; ensure `sslmode=require&channel_binding=require` in URL |
| Iframe Pi Dashboard blank | DevTools Network → check iframe src loads, status 200 | Verify `PI_API_BACKEND_URL` matches actual Vercel deploy URL; confirm CORS allows parent origin |
| AJAX `pi_api_refresh_jwt` returns 403 | DevTools Console / Network | Check user is admin (`current_user_can('manage_options')`); nonce hasn't expired |
| `/v1/ai/complete` returns 503 "no_providers" | Pool empty | Add real API keys per §2.2 |
| `/v1/ai/complete` returns 429 | Provider rate-limited | Add more keys to pool to round-robin; check `max_rpm` in `ai_providers` table |
| Worker (Celery) not picking up jobs | `railway logs --service pi-backend-worker` (if separate service) | Verify `CELERY_BROKER_URL` points to Upstash DB 1; check Upstash quota (500k cmds/month) |
| Mojibake `✓` / `→` errors on Windows seed | Default cmd cp1252 codec | Use `python -X utf8 -m scripts...` (already documented in §2.3) |
| License inactive after activate | Pi API → License page shows "active" but Dashboard shows error | Check `pi_api_jwt_expires_at` option in WP DB; rotate by deactivate + reactivate |

---

## 5. 📚 Related docs

- [DEPLOYMENT.md](./DEPLOYMENT.md) — Topology (Railway + Neon + Upstash + Vercel)
- [.env.example](./.env.example) — Full env var reference
- [`/plugins/pi-api/DOCS.md`](../plugins/pi-api/DOCS.md) — pi-api plugin architecture
- [`.task-handoffs/archive/2026-05/T-20260517-005-*.md`](../.task-handoffs/archive/2026-05/T-20260517-005-claude-remove-pi-dashboard-and-optimize-iframe.md) — Iframe security hardening rationale
- [`.task-handoffs/archive/2026-05/T-20260517-008-*.md`](../.task-handoffs/archive/2026-05/T-20260517-008-claude-switch-pi-api-to-vercel-url.md) — URL switch context

---

## 6. ⏭️ Next session

Bước em recommend lần tới (theo thứ tự):
1. **Rotate 3 secrets** (§2.1) — ~3 phút
2. **Add 3 real API keys** Groq + Gemini + Cerebras (§2.2) — ~10 phút
3. **Reallocate keys to admin license** (§2.3) — ~1 phút
4. **Smoke test pi-api** trên saigonhouse.local (§2.4) — ~5 phút end-to-end

Sau đó pi-ecosystem ready cho customer đầu tiên cài plugin + use AI features.
