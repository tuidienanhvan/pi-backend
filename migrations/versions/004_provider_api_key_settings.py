"""provider api_key + app_settings table

Revision ID: 004_provider_api_key_settings
Revises: 003_users
Create Date: 2026-04-17 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_provider_api_key_settings"
down_revision: Union[str, None] = "003_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add api_key column to ai_providers (plaintext; admin-only access)
    op.add_column(
        "ai_providers",
        sa.Column("api_key", sa.String(500), nullable=False, server_default=""),
    )

    # 2. Create app_settings (singleton key-value store for global config)
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("ai_providers", "api_key")
