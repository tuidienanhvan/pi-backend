# Database Schema - 19 Tables

## NHÓM 1: LICENSE & SITES
- `licenses` - Quản lý license key, tier, expiry
- `sites` - WordPress site activations

## NHÓM 2: AI TOKEN ECONOMY  
- `ai_token_wallets` - Token balances
- `ai_token_ledger` - Transaction log
- `ai_usage` - AI request logs
- `ai_providers` - AI provider config
- `ai_provider_keys` - API key pool

## NHÓM 3: SUBSCRIPTIONS
- `ai_packages` - Package tiers
- `license_packages` - License subscriptions

## NHÓM 4: USERS & LOGS
- `users` - Dashboard accounts
- `audit_log` - Change tracking
- `admin_audit_log` - Admin logs
- `app_settings` - Config

## NHÓM 5: SAAS (TENANTS)
- `tenants` - Customer accounts
- `tokens` - Tenant balances
- `token_transactions` - Transactions

## NHÓM 6: UPDATES
- `plugin_releases` - Version zips
- `usage_logs` - API tracking