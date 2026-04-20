"""initial schema — licenses, sites, usage_logs, plugin_releases

Revision ID: 001_initial
Revises:
Create Date: 2026-04-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── licenses ───────────────────────────────────────────────────
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("plugin", sa.String(64), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("customer_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("tier", sa.String(16), nullable=False, server_default="free", index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active", index=True),
        sa.Column("max_sites", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── sites ──────────────────────────────────────────────────────
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("domain", sa.String(255), nullable=False, index=True),
        sa.Column("wp_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("php_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("plugin_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("license_id", "domain", name="uq_site_license_domain"),
    )

    # ── usage_logs ─────────────────────────────────────────────────
    op.create_table(
        "usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("endpoint", sa.String(64), nullable=False, index=True),
        sa.Column("site_domain", sa.String(255), nullable=False, server_default="", index=True),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_usage_logs_license_created",
        "usage_logs",
        ["license_id", "created_at"],
    )

    # ── plugin_releases ────────────────────────────────────────────
    op.create_table(
        "plugin_releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plugin_slug", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.String(32), nullable=False, index=True),
        sa.Column("tier_required", sa.String(16), nullable=False, server_default="free"),
        sa.Column("zip_path", sa.String(500), nullable=False),
        sa.Column("zip_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("zip_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_stable", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column("is_yanked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_php_version", sa.String(8), nullable=False, server_default="8.3"),
        sa.Column("min_wp_version", sa.String(8), nullable=False, server_default="6.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("plugin_slug", "version", name="uq_plugin_version"),
    )


def downgrade() -> None:
    op.drop_index("ix_usage_logs_license_created", table_name="usage_logs")
    op.drop_table("plugin_releases")
    op.drop_table("usage_logs")
    op.drop_table("sites")
    op.drop_table("licenses")
