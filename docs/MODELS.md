# Models Reference

## License Models (`app/shared/license/models.py`)

### License
- `id` (PK)
- `key` - Unique license key
- `plugin` - Plugin slug
- `email` - Customer email
- `tier` - free/pro/max/enterprise
- `status` - active/expired/revoked/suspended
- `max_sites` - Site limit
- `expires_at` - Expiration date

### Site
- `id` (PK)
- `license_id` (FK)
- `domain` - WordPress domain
- `wp_version`, `php_version`, `plugin_version`
- `is_active`

## AI Models (`app/pi_ai_cloud/models.py`)

### TokenWallet
- `license_id` (unique)
- `balance`, `lifetime_topup`, `lifetime_spend`
- `daily_limit`

### TokenLedger
- `wallet_id`
- `op` - topup/spend/refund/bonus/admin_adjust
- `delta`, `balance_after`
- `reference_type`, `reference_id`

### AiUsage
- `license_id`, `wallet_id`
- `input_tokens`, `output_tokens`
- `pi_tokens_charged`
- `latency_ms`, `status`

### AiProvider
- `slug` - gemini-free, groq-free
- `adapter` - openai_compat/anthropic/gemini
- `pi_tokens_per_input/output`
- `is_enabled`, `health_status`

### AiProviderKey
- `key_value` - Encrypted API key
- `status` - available/allocated/exhausted/banned
- `monthly_quota_tokens`, `monthly_used_tokens`

### AiPackage / LicensePackage
- Token quotas and subscription management