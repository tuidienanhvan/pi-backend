# PI Backend API Documentation

Complete API reference for PI WordPress plugin backend services.

## Base URL

```
https://api.pi.direct/pi/v1/
```

---

## License API (`/license`)

### POST `/pi/v1/license/verify`

Verify license validity. Called every 12-24h by plugin.

**Request Body:**
```json
{
  "key": "pi_abc123...",
  "site_url": "https://example.com",
  "plugin_version": "1.0.0",
  "wp_version": "6.4",
  "php_version": "8.2"
}
```

**Response:**
```json
{
  "success": true,
  "tier": "pro",
  "status": "active",
  "expires_at": "2025-12-31T00:00:00Z",
  "features": ["seo_bot_ai", "schema_pro_templates", ...]
}
```

### POST `/pi/v1/license/activate`

Activate license for a new site.

**Request Body:**
```json
{
  "key": "pi_abc123...",
  "site_url": "https://example.com"
}
```

**Response:**
```json
{
  "success": true,
  "site_id": 1,
  "activated_sites": 1,
  "max_sites": 1,
  "message": "Activated"
}
```

### POST `/pi/v1/license/deactivate`

Deactivate license for a site.

**Request Body:** Same as activate

**Response:**
```json
{
  "success": true
}
```

### GET `/pi/v1/license/stats`

Get detailed license statistics.

**Response:**
```json
{
  "key_prefix": "pi_abc123...",
  "tier": "pro",
  "status": "active",
  "email": "user@example.com",
  "max_sites": 1,
  "activated_sites": 1,
  "usage_this_month": 150,
  "quota_this_month": 1000,
  "expires_at": null,
  "package_slug": "starter",
  "package_name": "Starter Pack",
  "package_status": "active",
  "quota_limit": 10000,
  "quota_used": 500
}
```

---

## Content API (`/content`)

### GET `/pi/v1/content`

List posts/pages with filters.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `type` | string | post/page |
| `status` | string | any/publish/draft |
| `search` | string | Search term |
| `page` | int | Page number |
| `per_page` | int | Items per page |

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "title": "Post Title",
      "slug": "post-slug",
      "status": "publish",
      "date": "2024-01-15",
      "featured_image": "https://...",
      "seo_score": 92,
      "word_count": 1500,
      "comment_count": 5,
      "media_count": 3
    }
  ],
  "total": 100,
  "page": 1
}
```

---

## AI Cloud API (`/ai`)

### POST `/pi/v1/ai/usage`

Record AI usage and get token balance.

**Request Body:**
```json
{
  "tokens": 1000,
  "provider": "groq"
}
```

**Response:**
```json
{
  "success": true,
  "balance": 5000
}
```

### GET `/pi/v1/ai/packages`

List available AI packages.

**Response:**
```json
{
  "items": [
    {
      "slug": "starter",
      "display_name": "Starter Pack",
      "price_cents_monthly": 500,
      "token_quota_monthly": 10000
    }
  ]
}
```

---

## Update API (`/updates`)

### GET `/pi/v1/updates/latest`

Get latest plugin version info.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `plugin_slug` | string | Plugin identifier |
| `current_version` | string | Current installed version |

**Response:**
```json
{
  "version": "1.5.0",
  "download_url": "https://...",
  "changelog": "Bug fixes and improvements",
  "is_stable": true,
  "min_wp": "6.0",
  "min_php": "8.3"
}
```

---

## Authentication

### Headers

All requests require:
```
Authorization: Bearer {license_key}
Content-Type: application/json
```

### License Key

Sent in `Authorization` header or request body:
```json
{
  "key": "pi_abc123..."
}
```

---

## Error Responses

```json
{
  "detail": "License not found",
  "status_code": 404
}
```

| Status | Description |
|--------|-------------|
| 401 | License key missing/invalid |
| 403 | License expired/revoked |
| 404 | Resource not found |
| 409 | Max sites reached |
| 429 | Rate limit exceeded |
| 500 | Server error |

---

## Webhooks

Stripe webhook endpoint: `/pi/v1/billing/webhook`

Events handled:
- `invoice.payment_succeeded`
- `customer.subscription.updated`
- `customer.subscription.deleted`

---

## Rate Limits

| Tier | Requests/month |
|------|---------------|
| free | 100 |
| pro | 1000 |
| max | 10000 |
| enterprise | Unlimited |