"""pi_ai_cloud — token wallets, ledger, providers, usage

Revision ID: 002_pi_ai_cloud
Revises: 001_initial
Create Date: 2026-04-17 01:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_pi_ai_cloud"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ai_token_wallets ──
    op.create_table(
        "ai_token_wallets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
            index=True,
        ),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lifetime_topup", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lifetime_spend", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("daily_limit", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── ai_token_ledger ──
    op.create_table(
        "ai_token_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "wallet_id",
            sa.Integer(),
            sa.ForeignKey("ai_token_wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("op", sa.String(16), nullable=False, index=True),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False, server_default=""),
        sa.Column("reference_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_ledger_ref", "ai_token_ledger", ["reference_type", "reference_id"])

    # ── ai_providers ──
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("adapter", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("input_cost_per_mtok_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_cost_per_mtok_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pi_tokens_per_input", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pi_tokens_per_output", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("tier", sa.String(16), nullable=False, server_default="free", index=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_rpm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_tpd", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column("health_status", sa.String(16), nullable=False, server_default="healthy"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── ai_usage ──
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "wallet_id",
            sa.Integer(),
            sa.ForeignKey("ai_token_wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("ai_providers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("source_plugin", sa.String(32), nullable=False, server_default="", index=True),
        sa.Column("source_endpoint", sa.String(64), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pi_tokens_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upstream_cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("error_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_license_created", "ai_usage", ["license_id", "created_at"])
    op.create_index("ix_ai_usage_plugin_created", "ai_usage", ["source_plugin", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_plugin_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_license_created", table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_table("ai_providers")
    op.drop_index("ix_ai_ledger_ref", table_name="ai_token_ledger")
    op.drop_table("ai_token_ledger")
    op.drop_table("ai_token_wallets")
