"""add routing policy fields to ai_packages

Adds package-driven routing: routing_mode, allowed_tiers, priority_boost,
dedicated_key_count. Additive only — safe rollback via downgrade.

Revision ID: 009_routing_policy
Revises: eabfff3ba783
Create Date: 2026-05-13 12:00:00.000000

Part of T-20260513-001 — AI Provider Routing Optimization.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_routing_policy"
down_revision: Union[str, None] = "eabfff3ba783"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # routing_mode: shared | dedicated | hybrid
    op.add_column(
        "ai_packages",
        sa.Column(
            "routing_mode",
            sa.String(length=16),
            nullable=False,
            server_default="shared",
        ),
    )
    op.create_index(
        "ix_ai_packages_routing_mode",
        "ai_packages",
        ["routing_mode"],
    )

    # allowed_tiers: JSON array of "free" | "paid"
    op.add_column(
        "ai_packages",
        sa.Column(
            "allowed_tiers",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[\"free\"]'"),
        ),
    )

    # priority_boost: int, higher = earlier in queue
    op.add_column(
        "ai_packages",
        sa.Column(
            "priority_boost",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # dedicated_key_count: auto-allocate target when routing_mode != shared
    op.add_column(
        "ai_packages",
        sa.Column(
            "dedicated_key_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Sensible defaults for existing packages by slug heuristic
    # (admin can override afterward via /v1/admin/packages PATCH)
    op.execute(
        """
        UPDATE ai_packages
           SET allowed_tiers = '["free","paid"]',
               priority_boost = 50,
               dedicated_key_count = 3,
               routing_mode = 'hybrid'
         WHERE slug IN ('enterprise', 'agency', 'max')
        """
    )
    op.execute(
        """
        UPDATE ai_packages
           SET allowed_tiers = '["free","paid"]',
               priority_boost = 20,
               routing_mode = 'shared'
         WHERE slug IN ('pro', 'plus')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ai_packages_routing_mode", table_name="ai_packages")
    op.drop_column("ai_packages", "dedicated_key_count")
    op.drop_column("ai_packages", "priority_boost")
    op.drop_column("ai_packages", "allowed_tiers")
    op.drop_column("ai_packages", "routing_mode")
