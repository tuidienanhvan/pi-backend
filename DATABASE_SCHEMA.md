# Database Schema Documentation

Complete documentation of all database models, tables, fields, and relationships.

## Overview

- **Total Models**: 19
- **Primary Key Pattern**: Auto-increment Integer (except `AuditLog` uses BigInteger)
- **Timestamp Pattern**: `TimestampMixin` provides `created_at`, `updated_at`
- **Soft Delete**: None (hard delete with `ondelete="CASCADE"`)

---

## NHÓM 1: LICENSE & CORE AUTH

### licenses

**Table**: `licenses`  
**File**: `app/shared/license/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `key` | String(64) | UNIQUE, INDEX, NOT NULL | License key (pi_xxxxx) |
| `plugin` | String(64) | INDEX, NOT NULL | Plugin slug (pi-seo-pro, pi-dashboard-pro) |
| `email` | String(255) | INDEX, NOT NULL | Customer email |
| `customer_name` | String(255) |  | Customer full name |
| `tier` | String(16) | INDEX, DEFAULT "free" | License tier (free, pro, max, enterprise) |
| `status` | String(16) | INDEX, DEFAULT "active" | Status (active, expired, revoked, suspended) |
| `max_sites` | Integer | DEFAULT 1 | Maximum activated sites |
| `expires_at` | DateTime(timezone=True) | NULLABLE | Expiration date |
| `stripe_customer_id` | String(64) | NULLABLE | Stripe customer ID |
| `stripe_subscription_id` | String(64) | NULLABLE | Stripe subscription ID |
| `notes` | String(1000) | DEFAULT "" | Admin notes |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

**Relationships**:
- `sites` → List[Site] (one-to-many, cascade delete)

---

### sites

**Table**: `sites`  
**File**: `app/shared/license/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `license_id` | Integer | FK → licenses.id, INDEX | Owner license |
| `domain` | String(255) | INDEX, NOT NULL | WordPress site domain (normalized) |
| `wp_version` | String(32) | DEFAULT "" | WordPress version |
| `php_version` | String(32) | DEFAULT "" | PHP version |
| `plugin_version` | String(32) | DEFAULT "" | Plugin version |
| `last_seen_at` | DateTime(timezone=True) | NULLABLE | Last heartbeat |
| `is_active` | Boolean | DEFAULT True | Site still active |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

**Constraints**:
- `UniqueConstraint("license_id", "domain", name="uq_site_license_domain")`

**Relationships**:
- `license` → License (many-to-one)

---

## NHÓM 2: AI TOKEN ECONOMY

### ai_token_wallets

**Table**: `ai_token_wallets`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `license_id` | Integer | FK → licenses.id, UNIQUE, INDEX | Owner license |
| `balance` | BigInteger | DEFAULT 0, NOT NULL | Current token balance |
| `lifetime_topup` | BigInteger | DEFAULT 0 | Total tokens ever added |
| `lifetime_spend` | BigInteger | DEFAULT 0 | Total tokens spent |
| `daily_limit` | BigInteger | DEFAULT 0 | Daily spend limit (0 = unlimited) |
| `last_activity_at` | DateTime(timezone=True) | NULLABLE | Last transaction time |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

**Relationships**:
- `ledger_entries` → List[TokenLedger] (one-to-many, cascade delete)

---

### ai_token_ledger

**Table**: `ai_token_ledger`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `wallet_id` | Integer | FK → ai_token_wallets.id, INDEX | Owner wallet |
| `op` | String(16) | INDEX, NOT NULL | Operation (topup, spend, refund, bonus, admin_adjust) |
| `delta` | BigInteger | NOT NULL | Token change amount |
| `balance_after` | BigInteger | NOT NULL | Balance after transaction |
| `reference_type` | String(32) | DEFAULT "" | Reference type (stripe_payment, ai_usage, promo) |
| `reference_id` | String(128) | DEFAULT "" | Reference ID |
| `note` | String(500) | DEFAULT "" | Transaction note |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

**Relationships**:
- `wallet` → TokenWallet (many-to-one)

---

### ai_usage

**Table**: `ai_usage`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `license_id` | Integer | FK → licenses.id, INDEX | License used |
| `wallet_id` | Integer | FK → ai_token_wallets.id, INDEX | Wallet charged |
| `provider_id` | Integer | FK → ai_providers.id, NULLABLE, INDEX | AI provider |
| `provider_key_id` | Integer | FK → ai_provider_keys.id, NULLABLE, INDEX | API key used |
| `source_plugin` | String(32) | INDEX, DEFAULT "" | Source (pi-seo, pi-chatbot, pi-leads) |
| `source_endpoint` | String(64) | DEFAULT "" | Endpoint (seo_bot.generate, etc.) |
| `input_tokens` | Integer | DEFAULT 0 | Input token count |
| `output_tokens` | Integer | DEFAULT 0 | Output token count |
| `pi_tokens_charged` | Integer | DEFAULT 0 | Pi tokens deducted |
| `upstream_cost_cents` | Integer | DEFAULT 0 | Actual upstream cost |
| `latency_ms` | Integer | DEFAULT 0 | Response latency |
| `status` | String(16) | DEFAULT "success" | Request status |
| `error_code` | String(64) | DEFAULT "" | Error code if failed |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## NHÓM 3: AI INFRASTRUCTURE

### ai_providers

**Table**: `ai_providers`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `slug` | String(64) | UNIQUE, INDEX | Provider slug (gemini-free, groq-free) |
| `display_name` | String(128) |  | Display name |
| `adapter` | String(32) |  | Adapter class (openai_compat, anthropic, gemini) |
| `base_url` | String(500) |  | API base URL |
| `model_id` | String(128) |  | Upstream model ID |
| `input_cost_per_mtok_cents` | Integer | DEFAULT 0 | Cost per 1M input tokens |
| `output_cost_per_mtok_cents` | Integer | DEFAULT 0 | Cost per 1M output tokens |
| `pi_tokens_per_input` | Float | DEFAULT 1.0 | Pi tokens per input token |
| `pi_tokens_per_output` | Float | DEFAULT 1.0 | Pi tokens per output token |
| `tier` | String(16) | INDEX, DEFAULT "free" | Routing tier |
| `priority` | Integer | DEFAULT 100 | Routing priority (lower = tried first) |
| `max_rpm` | Integer | DEFAULT 0 | Max requests per minute |
| `max_tpd` | Integer | DEFAULT 0 | Max tokens per day |
| `is_enabled` | Boolean | DEFAULT True | Provider enabled |
| `health_status` | String(16) | DEFAULT "healthy" | Health (healthy, degraded, down) |
| `last_error` | Text | DEFAULT "" | Last error message |
| `last_success_at` | DateTime(timezone=True) | NULLABLE | Last success time |
| `last_failure_at` | DateTime(timezone=True) | NULLABLE | Last failure time |
| `consecutive_failures` | Integer | DEFAULT 0 | Failure count |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

### ai_provider_keys

**Table**: `ai_provider_keys`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `provider_id` | Integer | FK → ai_providers.id, INDEX | Owner provider |
| `key_value` | String(500) | NOT NULL | Encrypted API key |
| `label` | String(128) | DEFAULT "" | Admin-readable label |
| `status` | String(16) | INDEX, DEFAULT "available" | (available, allocated, exhausted, banned) |
| `allocated_to_license_id` | Integer | FK → licenses.id, NULLABLE, INDEX | Allocated license |
| `allocated_at` | DateTime(timezone=True) | NULLABLE | Allocation time |
| `health_status` | String(16) | DEFAULT "healthy" | Key health |
| `consecutive_failures` | Integer | DEFAULT 0 | Failure count |
| `last_success_at` | DateTime(timezone=True) | NULLABLE | Last success |
| `last_failure_at` | DateTime(timezone=True) | NULLABLE | Last failure |
| `last_error` | Text | DEFAULT "" | Last error |
| `monthly_used_tokens` | BigInteger | DEFAULT 0 | Monthly usage |
| `monthly_quota_tokens` | BigInteger | DEFAULT 0 | Monthly quota |
| `period_started_at` | DateTime(timezone=True) |  | Period start |
| `notes` | Text | DEFAULT "" | Admin notes |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## NHÓM 4: SUBSCRIPTIONS & PACKAGES

### ai_packages

**Table**: `ai_packages`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `slug` | String(32) | PK | Package identifier (starter, pro, enterprise) |
| `display_name` | String(64) | NOT NULL | Display name |
| `description` | String(500) | DEFAULT "" | Package description |
| `price_cents_monthly` | Integer | DEFAULT 0 | Monthly price in cents |
| `price_cents_yearly` | Integer | DEFAULT 0 | Yearly price in cents |
| `token_quota_monthly` | BigInteger | DEFAULT 0 | Monthly token quota |
| `allowed_qualities` | JSON | NOT NULL | Quality levels (["fast"], ["fast","balanced"]) |
| `features` | JSON | DEFAULT [] | Feature list |
| `sort_order` | Integer | DEFAULT 100 | Display order |
| `is_active` | Boolean | DEFAULT True | Available for purchase |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

### license_packages

**Table**: `license_packages`  
**File**: `app/pi_ai_cloud/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `license_id` | Integer | PK, FK → licenses.id | License |
| `package_slug` | String(32) | FK → ai_packages.slug, INDEX | Package type |
| `status` | String(16) | DEFAULT "active" | (active, past_due, cancelled) |
| `activated_at` | DateTime(timezone=True) |  | Activation time |
| `renews_at` | DateTime(timezone=True) | NULLABLE | Next renewal |
| `expires_at` | DateTime(timezone=True) | NULLABLE | Expiration |
| `stripe_subscription_id` | String(128) | DEFAULT "" | Stripe subscription |
| `current_period_started_at` | DateTime(timezone=True) |  | Period start |
| `current_period_tokens_used` | BigInteger | DEFAULT 0 | Period usage |
| `current_period_requests` | Integer | DEFAULT 0 | Period requests |
| `lifetime_tokens_used` | BigInteger | DEFAULT 0 | Lifetime usage |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## NHÓM 5: USERS & AUTH

### users

**Table**: `users`  
**File**: `app/shared/auth/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `email` | String(255) | UNIQUE, INDEX, NOT NULL | Login email |
| `name` | String(255) | DEFAULT "" | Full name |
| `password_hash` | String(255) | NOT NULL | bcrypt hash |
| `is_admin` | Boolean | DEFAULT False | Admin rights |
| `is_verified` | Boolean | DEFAULT False | Email verified |
| `is_active` | Boolean | DEFAULT True | Account active |
| `last_login_at` | DateTime(timezone=True) | NULLABLE | Last login |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## NHÓM 6: ADMIN & LOGS

### audit_log

**Table**: `audit_log`  
**File**: `app/admin/audit.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigInteger | PK | Primary key |
| `actor_id` | Integer | FK → users.id, NULLABLE, INDEX | Actor user |
| `actor_email` | String(255) | DEFAULT "" | Actor email |
| `action` | String(32) | INDEX | (CREATE, UPDATE, DELETE) |
| `resource_type` | String(32) | INDEX | Resource type |
| `resource_id` | String(64) | INDEX, DEFAULT "" | Resource ID |
| `resource_label` | String(255) | DEFAULT "" | Resource label |
| `before` | JSON | NULLABLE | Before data |
| `after` | JSON | NULLABLE | After data |
| `ip_address` | String(64) | DEFAULT "" | Request IP |
| `user_agent` | String(500) | DEFAULT "" | User agent |
| `request_id` | String(64) | DEFAULT "" | Request ID |
| `message` | String(500) | DEFAULT "" | Log message |
| `severity` | String(16) | INDEX, DEFAULT "info" | Severity level |
| `created_at` | DateTime(timezone=True) | INDEX | Timestamp |

---

### admin_audit_log

**Table**: `admin_audit_log`  
**File**: `app/saas/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `actor` | String(255) | DEFAULT "system", INDEX | Actor name |
| `action` | String(96) | INDEX | Action performed |
| `tenant_id` | Integer | NULLABLE, INDEX | Related tenant |
| `metadata` | JSON | DEFAULT {}, NOT NULL | Extra data |
| `created_at` | DateTime(timezone=True) | NOT NULL | Timestamp |

---

### app_settings

**Table**: `app_settings`  
**File**: `app/admin/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `key` | String(64) | PK | Setting key |
| `value` | JSON | NOT NULL | Setting value |
| `updated_at` | DateTime(timezone=True) | NOT NULL | Update timestamp |

---

## NHÓM 7: MULTI-TENANT (SAAS)

### tenants

**Table**: `tenants`  
**File**: `app/saas/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `name` | String(255) | DEFAULT "" | Tenant name |
| `license_key` | String(96) | UNIQUE, INDEX, NOT NULL | License key |
| `domain` | String(255) | UNIQUE, INDEX, NOT NULL | Domain |
| `site_url` | String(500) | DEFAULT "" | Site URL |
| `tier` | String(32) | DEFAULT "free", INDEX | (free, pro, max) |
| `status` | String(32) | DEFAULT "active", INDEX | Status |
| `stripe_subscription_id` | String(255) | UNIQUE, NULLABLE | Stripe ID |
| `subscription_status` | String(50) | NULLABLE | Subscription status |
| `subscription_current_period_end` | DateTime(timezone=True) | NULLABLE | Period end |
| `is_admin` | Boolean | DEFAULT False | Admin tenant |
| `features` | JSON | DEFAULT [], NOT NULL | Enabled features |
| `wp_version` | String(32) | DEFAULT "" | WP version |
| `plugin_version` | String(32) | DEFAULT "" | Plugin version |
| `activated_at` | DateTime(timezone=True) | NULLABLE | Activation |
| `expires_at` | DateTime(timezone=True) | NULLABLE | Expiration |
| `last_seen_at` | DateTime(timezone=True) | NULLABLE | Last seen |
| `metadata` | JSON | DEFAULT {}, NOT NULL | Extra data |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

### tokens

**Table**: `tokens`  
**File**: `app/saas/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `tenant_id` | Integer | FK → tenants.id, INDEX | Owner tenant |
| `balance` | Integer | DEFAULT 0, NOT NULL | Token balance |
| `monthly_quota` | Integer | DEFAULT 0, NOT NULL | Monthly quota |
| `used_this_month` | Integer | DEFAULT 0, NOT NULL | Used this month |
| `reset_at` | DateTime(timezone=True) | NULLABLE | Reset time |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

### token_transactions

**Table**: `token_transactions`  
**File**: `app/saas/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `tenant_id` | Integer | FK → tenants.id, INDEX | Owner tenant |
| `delta` | Integer | NOT NULL | Token change |
| `reason` | String(64) | DEFAULT "manual" | Reason |
| `note` | Text | DEFAULT "" | Note |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## NHÓM 8: LOGS & TRACKING

### usage_logs

**Table**: `usage_logs`  
**File**: `app/shared/usage.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `license_id` | Integer | FK → licenses.id, INDEX | License |
| `endpoint` | String(64) | INDEX | Endpoint path |
| `site_domain` | String(255) | DEFAULT "", INDEX | Site domain |
| `tokens_input` | Integer | DEFAULT 0 | Input tokens |
| `tokens_output` | Integer | DEFAULT 0 | Output tokens |
| `cost_cents` | Integer | DEFAULT 0 | Cost in cents |
| `status` | String(16) | DEFAULT "success" | (success, error, rate_limited) |
| `latency_ms` | Integer | DEFAULT 0 | Latency |
| `error_message` | Text | DEFAULT "" | Error message |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## NHÓM 9: PLUGIN UPDATES

### plugin_releases

**Table**: `plugin_releases`  
**File**: `app/shared/updates/models.py`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK | Primary key |
| `plugin_slug` | String(64) | INDEX, NOT NULL | Plugin slug |
| `version` | String(32) | INDEX, NOT NULL | Semantic version |
| `tier_required` | String(16) | DEFAULT "free" | Required tier |
| `zip_path` | String(500) | NOT NULL | ZIP file path |
| `zip_size_bytes` | BigInteger | DEFAULT 0 | File size |
| `zip_sha256` | String(64) | DEFAULT "" | SHA256 hash |
| `changelog` | Text | DEFAULT "" | Change notes |
| `is_stable` | Boolean | DEFAULT True | Stable release |
| `is_yanked` | Boolean | DEFAULT False | Yanked release |
| `min_php_version` | String(8) | DEFAULT "8.3" | Min PHP |
| `min_wp_version` | String(8) | DEFAULT "6.0" | Min WP |
| `created_at` | DateTime(timezone=True) |  | Creation timestamp |
| `updated_at` | DateTime(timezone=True) |  | Update timestamp |

---

## Relationship Diagram

```
licenses (1) ──< sites
    │
    └── (1) ── ai_token_wallets (1) ──< ai_token_ledger
    │               │
    │               └── (1) ──< ai_usage
    │
    └── (1) ── license_packages >── ai_packages
    │
    └── (1) ── users (via email)

ai_providers (1) ──< ai_provider_keys
    │
    └── (1) ──< ai_usage

tenants (1) ──< tokens
    │       └── (1) ──< token_transactions
    │       └── (1) ──< admin_audit_log

AuditLog ── users (via actor_id)
```

---

## Index Summary

**Most Queried Fields (Indexed)**:
- `licenses.key`, `licenses.email`, `licenses.plugin`
- `sites.license_id`, `sites.domain`
- `ai_token_wallets.license_id`
- `ai_usage.license_id`, `ai_usage.provider_id`
- `ai_provider_keys.provider_id`, `ai_provider_keys.status`
- `tenants.license_key`, `tenants.domain`

---

## Generated: 2026-05-05