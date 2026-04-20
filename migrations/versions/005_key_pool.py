"""ai_provider_keys pool + ai_packages + license_packages

Architecture: Pi manages a POOL of upstream API keys. Admin allocates N keys
from the pool to each customer (license). Customer's router uses ONLY their
allocated keys — zero sharing between customers. Customer sees token quota
only; never sees the keys themselves.

Revision ID: 005_key_pool
Revises: 004_provider_api_key_settings
Create Date: 2026-04-17 13:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_key_pool"
down_revision: Union[str, None] = "004_provider_api_key_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. ai_provider_keys — pool of upstream API keys
    op.create_table(
        "ai_provider_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key_value", sa.String(500), nullable=False),  # encrypted at rest (app layer)
        sa.Column("label", sa.String(128), nullable=False, server_default=""),  # "groq-acct-17-sim-0909xxx"
        sa.Column("status", sa.String(16), nullable=False, server_default="available", index=True),
        # 'available' | 'allocated' | 'exhausted' | 'banned'
        sa.Column("allocated_to_license_id", sa.Integer(), sa.ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),

        # Health
        sa.Column("health_status", sa.String(16), nullable=False, server_default="healthy"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),

        # Quota accounting (per-key monthly)
        sa.Column("monthly_used_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("monthly_quota_tokens", sa.BigInteger(), nullable=False, server_default="0"),  # 0 = unlimited
        sa.Column("period_started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_provider_keys_status_health", "ai_provider_keys", ["status", "health_status"])

    # 2. ai_packages — customer-facing subscription tiers
    op.create_table(
        "ai_packages",
        sa.Column("slug", sa.String(32), primary_key=True),  # 'free'|'starter'|'pro'|'agency'|'enterprise'
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("price_cents_monthly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_cents_yearly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_quota_monthly", sa.BigInteger(), nullable=False, server_default="0"),  # 0 = unlimited
        sa.Column("allowed_qualities", sa.JSON(), nullable=False),  # ["fast", "balanced", "best"]
        sa.Column("features", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),  # marketing bullets
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 3. license_packages — which package each license has + usage counter
    op.create_table(
        "license_packages",
        sa.Column("license_id", sa.Integer(), sa.ForeignKey("licenses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("package_slug", sa.String(32), sa.ForeignKey("ai_packages.slug"), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),  # active|past_due|cancelled
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("renews_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(128), nullable=False, server_default=""),

        # Current billing period accounting
        sa.Column("current_period_started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("current_period_tokens_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("current_period_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_tokens_used", sa.BigInteger(), nullable=False, server_default="0"),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 4. ai_usage — add provider_key_id column so we can attribute calls to specific keys
    op.add_column(
        "ai_usage",
        sa.Column("provider_key_id", sa.Integer(), sa.ForeignKey("ai_provider_keys.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    # 5. MIGRATE existing ai_providers.api_key values into new pool (1 key per provider)
    #    This preserves behavior: keys Pi team already typed via /admin UI still work.
    op.execute("""
        INSERT INTO ai_provider_keys (provider_id, key_value, label, status, created_at, updated_at)
        SELECT id, api_key, 'migrated-from-provider-row', 'available', NOW(), NOW()
        FROM ai_providers
        WHERE api_key IS NOT NULL AND api_key <> ''
    """)

    # 6. Drop api_key column from ai_providers (keys now live in ai_provider_keys)
    op.drop_column("ai_providers", "api_key")


def downgrade() -> None:
    # Restore api_key column (lossy — only 1 key per provider)
    op.add_column("ai_providers", sa.Column("api_key", sa.String(500), nullable=False, server_default=""))
    op.execute("""
        UPDATE ai_providers p
        SET api_key = (
            SELECT key_value FROM ai_provider_keys k
            WHERE k.provider_id = p.id
            ORDER BY k.id LIMIT 1
        )
        WHERE EXISTS (SELECT 1 FROM ai_provider_keys k WHERE k.provider_id = p.id)
    """)

    op.drop_column("ai_usage", "provider_key_id")
    op.drop_table("license_packages")
    op.drop_table("ai_packages")
    op.drop_index("ix_ai_provider_keys_status_health", table_name="ai_provider_keys")
    op.drop_table("ai_provider_keys")
