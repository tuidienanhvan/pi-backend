# Database Schema

## Tables by Category

### License & Sites
- `licenses` - Key, email, tier, expiry
- `sites` - Activated domains

### AI Economy  
- `ai_token_wallets` - Balance tracking
- `ai_token_ledger` - Transaction log
- `ai_usage` - Request logging
- `ai_providers` - AI provider config
- `ai_provider_keys` - API key pool
- `ai_packages` - Subscription tiers
- `license_packages` - License subscriptions

### Users & Logs
- `users` - Dashboard accounts
- `audit_log` - Change tracking
- `admin_audit_log` - Admin actions
- `app_settings` - Config key-value
- `usage_logs` - API tracking

### Multi-Tenant (SaaS)
- `tenants` - Customer accounts
- `tokens` - Tenant balances
- `token_transactions` - Tenant transactions

### Updates
- `plugin_releases` - Version zips