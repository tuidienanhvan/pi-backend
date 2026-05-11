"""add SaaS tenants and tenant scoping

Revision ID: 007_add_saas_tenants
Revises: 006_audit_log
Create Date: 2026-04-28 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_add_saas_tenants"
down_revision: Union[str, None] = "006_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_TO_SCOPE = [
    "usage_logs",
    "ai_token_wallets",
    "ai_token_ledger",
    "ai_usage",
    "provider_api_keys",
]


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False, server_default=""),
            sa.Column("license_key", sa.String(96), nullable=False),
            sa.Column("domain", sa.String(255), nullable=False),
            sa.Column("site_url", sa.String(500), nullable=False, server_default=""),
            sa.Column("tier", sa.String(32), nullable=False, server_default="free"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("features", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("wp_version", sa.String(32), nullable=False, server_default=""),
            sa.Column("plugin_version", sa.String(32), nullable=False, server_default=""),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "tier IN ('free', 'pro', 'max', 'enterprise')",
                name="ck_tenants_tier",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'inactive', 'suspended', 'revoked', 'expired')",
                name="ck_tenants_status",
            ),
            sa.UniqueConstraint("license_key", name="uq_tenants_license_key"),
            sa.UniqueConstraint("domain", name="uq_tenants_domain"),
        )
        op.create_index("idx_tenants_license", "tenants", ["license_key"])
        op.create_index("idx_tenants_domain", "tenants", ["domain"])
        op.execute(
            """
            INSERT INTO tenants (
                id, name, license_key, domain, site_url, tier, status, is_admin,
                features, activated_at, last_seen_at
            )
            VALUES (
                1, 'Pi Ecosystem Admin', 'ADMIN-MASTER-DO-NOT-SHARE-XX',
                'saigonhouse.local', 'http://saigonhouse.local', 'enterprise',
                'active', TRUE,
                '["ai_chatbot","seo_audit","lead_pipeline","analytics","multi_site","white_label","devops"]',
                NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
            """
        )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "tokens"):
        op.create_table(
            "tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("monthly_quota", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used_this_month", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_tokens_tenant", "tokens", ["tenant_id"])
        op.execute(
            """
            INSERT INTO tokens (tenant_id, balance, monthly_quota, used_this_month)
            VALUES (1, 999999, 999999, 0)
            """
        )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "token_transactions"):
        op.create_table(
            "token_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(64), nullable=False, server_default="manual"),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_token_transactions_tenant_created", "token_transactions", ["tenant_id", "created_at"])

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "admin_audit_log"):
        op.create_table(
            "admin_audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor", sa.String(255), nullable=False, server_default="system"),
            sa.Column("action", sa.String(96), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_admin_audit_actor", "admin_audit_log", ["actor"])
        op.create_index("idx_admin_audit_tenant_created", "admin_audit_log", ["tenant_id", "created_at"])

    inspector = sa.inspect(bind)
    for table_name in TABLES_TO_SCOPE:
        if not _table_exists(inspector, table_name) or _column_exists(inspector, table_name, "tenant_id"):
            continue
        op.add_column(
            table_name,
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id"),
                nullable=False,
                server_default="1",
            ),
        )
        index_name = f"idx_{table_name}_tenant"
        if not _index_exists(sa.inspect(bind), table_name, index_name):
            op.create_index(index_name, table_name, ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in reversed(TABLES_TO_SCOPE):
        if not _table_exists(inspector, table_name) or not _column_exists(inspector, table_name, "tenant_id"):
            continue
        index_name = f"idx_{table_name}_tenant"
        if _index_exists(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        op.drop_column(table_name, "tenant_id")
        inspector = sa.inspect(bind)

    if _table_exists(inspector, "admin_audit_log"):
        if _index_exists(inspector, "admin_audit_log", "idx_admin_audit_tenant_created"):
            op.drop_index("idx_admin_audit_tenant_created", table_name="admin_audit_log")
        if _index_exists(inspector, "admin_audit_log", "idx_admin_audit_actor"):
            op.drop_index("idx_admin_audit_actor", table_name="admin_audit_log")
        op.drop_table("admin_audit_log")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "token_transactions"):
        if _index_exists(inspector, "token_transactions", "idx_token_transactions_tenant_created"):
            op.drop_index("idx_token_transactions_tenant_created", table_name="token_transactions")
        op.drop_table("token_transactions")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "tokens"):
        if _index_exists(inspector, "tokens", "idx_tokens_tenant"):
            op.drop_index("idx_tokens_tenant", table_name="tokens")
        op.drop_table("tokens")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "tenants"):
        if _index_exists(inspector, "tenants", "idx_tenants_domain"):
            op.drop_index("idx_tenants_domain", table_name="tenants")
        if _index_exists(inspector, "tenants", "idx_tenants_license"):
            op.drop_index("idx_tenants_license", table_name="tenants")
        op.drop_table("tenants")
