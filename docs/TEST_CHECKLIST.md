# Pi Ecosystem — End-to-end test checklist

Run these tests in order after deploying. Target: ~30 minutes to walk through all.

Set `$BACKEND` env var for curl commands:
```bash
export BACKEND=https://api.piwebagency.com       # or http://localhost:8000 for local
```

---

## 1. Health & readiness (no auth)

```bash
curl -i $BACKEND/health
# → HTTP/2 200, {"status":"ok"}

curl -i $BACKEND/ready
# → HTTP/2 200, {"status":"ok","database":"ok","redis":"ok"}

curl -i $BACKEND/
# → {"service":"pi-backend","version":"0.1.0","status":"ok","plugins":{...}}
```

---

## 2. User auth (dashboard JWT)

```bash
# Signup
curl -X POST $BACKEND/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!","name":"Test User"}'
# → {"token":"eyJ...","expires_in":604800,"user":{...}}

# Save the token:
export JWT="eyJ..."

# Verify /me
curl $BACKEND/v1/auth/me -H "Authorization: Bearer $JWT"
# → {"id":1,"email":"test@example.com","is_admin":false,"license_count":0,"token_balance":0}

# Login
curl -X POST $BACKEND/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!"}'
# → new token with same payload

# Wrong password
curl -X POST $BACKEND/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrong"}'
# → HTTP 401, {"code":"invalid_credentials"}
```

---

## 3. Admin auth (promote user to admin)

```bash
# Create admin via CLI
railway run python -m scripts.create_admin \
    --email admin@example.com --password "AdminPass123!" --name "Admin"

# Login as admin
curl -X POST $BACKEND/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"AdminPass123!"}'
export ADMIN_JWT="eyJ..."

# Access admin overview (should work)
curl $BACKEND/v1/admin/overview -H "Authorization: Bearer $ADMIN_JWT"
# → {"revenue_30d":0,"active_licenses":0,...}

# Access admin overview as regular user (should fail)
curl $BACKEND/v1/admin/overview -H "Authorization: Bearer $JWT"
# → HTTP 403 "Admin access required"
```

---

## 4. License lifecycle (admin creates → customer uses)

```bash
# Admin creates license for customer
curl -X POST $BACKEND/v1/admin/licenses \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"plugin":"pi-seo-pro","email":"customer@test.com","tier":"pro","max_sites":1,"expires_days":365}'
# → {"id":1,"key":"pi_abc123...","email":"customer@test.com",...}

export LICENSE_KEY="pi_abc123..."

# Customer activates site
curl -X POST $BACKEND/v1/license/activate \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"site_url":"https://demo.local","plugin_version":"2.0.0","wp_version":"6.5","php_version":"8.3"}'
# → {"success":true,"site_id":1,"activated_sites":1,"max_sites":1,"message":"Activated"}

# Verify license (daily heartbeat)
curl -X POST $BACKEND/v1/license/verify \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"site_url":"https://demo.local","plugin_version":"2.0.0"}'
# → {"success":true,"tier":"pro","status":"active","features":[...]}

# Stats
curl $BACKEND/v1/license/stats -H "Authorization: Bearer $LICENSE_KEY"
# → {"tier":"pro","activated_sites":1,"max_sites":1,...}
```

---

## 5. Pi AI Cloud (tokens)

```bash
# Check wallet (auto-creates with 1,000 free bonus)
curl $BACKEND/v1/ai/wallet -H "Authorization: Bearer $LICENSE_KEY"
# → {"balance":1000,"lifetime_topup":1000,"lifetime_spend":0,...}

# Available packs
curl $BACKEND/v1/ai/topup/packs
# → {"packs":[{"id":"10k","tokens":10000,"price_usd":1.0},...]}

# Make an AI completion call (spends ~10-100 tokens)
curl -X POST $BACKEND/v1/ai/complete \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role":"system","content":"You are helpful."},
      {"role":"user","content":"Say hi in Vietnamese"}
    ],
    "max_tokens": 50,
    "quality": "fast",
    "source_plugin": "pi-seo-pro"
  }'
# → {"success":true,"text":"Chào bạn!","pi_tokens_charged":42,"wallet_balance_after":958,"provider_used":"groq-llama-70b-free"}

# Ledger
curl "$BACKEND/v1/ai/ledger?limit=10" -H "Authorization: Bearer $LICENSE_KEY"
# → {"entries":[{"op":"spend","delta":-42,"balance_after":958,...},{"op":"bonus","delta":1000,...}]}

# Stripe Checkout (creates session, returns redirect URL)
curl -X POST $BACKEND/v1/ai/topup/checkout \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pack":"100k","success_url":"https://store.pi-ecosystem.com/app/wallet?topup=success","cancel_url":"https://store.pi-ecosystem.com/app/wallet?topup=cancel"}'
# → {"session_id":"cs_test_...","checkout_url":"https://checkout.stripe.com/..."}
```

---

## 6. Pi SEO endpoints

```bash
# SEO Bot generate
curl -X POST $BACKEND/v1/seo/bot/generate \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "site_url":"https://demo.local",
    "post_id":1,
    "post_title":"Hướng dẫn SEO WordPress cơ bản",
    "focus_keyword":"SEO WordPress",
    "excerpt":"Bài viết này sẽ chỉ bạn cách tối ưu SEO...",
    "tone":"professional",
    "language":"vi",
    "variants":2
  }'
# → {"variants":[{"title":"...","description":"..."}],"tokens_used":742,...}

# Audit run
curl -X POST $BACKEND/v1/seo/audit/run \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "site_url":"https://demo.local",
    "title":"Guide to WP SEO",
    "meta_description":"Complete guide to WordPress SEO with meta tags, schema, sitemaps.",
    "focus_keyword":"WordPress SEO",
    "html":"<html><head><title>Guide</title></head><body><h1>Guide</h1><p>'$(printf 'word %.0s' {1..400})'</p></body></html>"
  }'
# → {"score":75,"grade":"B","issues":[...]}

# Content analyze (readability)
curl -X POST $BACKEND/v1/seo/audit/content \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content":"This is a sample paragraph with enough text for analysis. Keyword density matters.","focus_keyword":"keyword","language":"en"}'
# → {"word_count":14,"readability_score":...,"keyword_density":...}

# Schema templates
curl $BACKEND/v1/seo/schema/templates -H "Authorization: Bearer $LICENSE_KEY"
# → {"templates":[{"id":"article-basic",...}],"total":10}
```

---

## 7. Admin dashboard endpoints

```bash
# Overview
curl $BACKEND/v1/admin/overview -H "Authorization: Bearer $ADMIN_JWT"

# Licenses
curl "$BACKEND/v1/admin/licenses?limit=10" -H "Authorization: Bearer $ADMIN_JWT"

# Users
curl "$BACKEND/v1/admin/users?limit=10" -H "Authorization: Bearer $ADMIN_JWT"

# Providers
curl $BACKEND/v1/admin/providers -H "Authorization: Bearer $ADMIN_JWT"

# Disable a provider
curl -X PATCH $BACKEND/v1/admin/providers/1 \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled":false}'

# Usage
curl "$BACKEND/v1/admin/usage?days=30" -H "Authorization: Bearer $ADMIN_JWT"

# Revenue
curl "$BACKEND/v1/admin/revenue?days=30" -H "Authorization: Bearer $ADMIN_JWT"

# Adjust tokens manually (support / refund)
curl -X POST $BACKEND/v1/admin/licenses/1/tokens \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"delta":5000,"note":"Support ticket #42"}'
```

---

## 8. Error handling smoke test

```bash
# Missing auth
curl $BACKEND/v1/ai/wallet
# → HTTP 401, "Missing Bearer token"

# Invalid license key
curl $BACKEND/v1/ai/wallet -H "Authorization: Bearer pi_fake"
# → HTTP 403, "License invalid or revoked"

# Insufficient tokens (drain wallet first, then call)
curl -X POST $BACKEND/v1/ai/complete \
  -H "Authorization: Bearer $LICENSE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Test"}],"max_tokens":10000}'
# → HTTP 402, {"code":"insufficient_tokens",...}

# Rate limit (hit burst limit)
for i in {1..20}; do
  curl -X POST $BACKEND/v1/ai/complete \
    -H "Authorization: Bearer $LICENSE_KEY" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Hi"}]}' &
done
wait
# After ~10 req/min, you should see HTTP 429 "rate_limit_exceeded"
```

---

## 9. Webhook test (Stripe)

```bash
# Using Stripe CLI (local)
stripe listen --forward-to localhost:8000/v1/ai/stripe/webhook

# In another terminal:
stripe trigger checkout.session.completed

# Check pi-backend logs:
# → {"wallet_topup","license_id":1,"tokens":100000,"session_id":"cs_..."}

# Verify wallet balance increased:
curl $BACKEND/v1/ai/wallet -H "Authorization: Bearer $LICENSE_KEY"
# → balance went up by 100_000 tokens
```

---

## 10. Frontend flow test

1. Open `https://store.pi-ecosystem.com` → catalog loads
2. Click any plugin → product detail
3. Fill lead form → submitted to n8n
4. Go to `/login` → sign in as admin
5. Verify redirect to `/admin`
6. Admin overview shows stats
7. Click `/admin/licenses` → list loads
8. Create a license → new key appears, copyable
9. Open incognito → sign in as normal user (customer email)
10. Verify `/app` overview shows licenses you created for that email
11. Visit `/app/wallet` → packs visible, click "Buy" → Stripe Checkout opens
12. Use Stripe test card `4242 4242 4242 4242` → success
13. Redirect back to `/app/wallet?topup=success` → balance updated

---

## Exit criteria

- [ ] All 10 test sections pass
- [ ] No 500 errors in Railway logs
- [ ] No Sentry errors
- [ ] Admin dashboard displays live data
- [ ] Customer can pay via Stripe + tokens land in wallet
- [ ] Plugin Pro feature (SEO Bot) actually works end-to-end

Once green: **you're live.** 🚀
