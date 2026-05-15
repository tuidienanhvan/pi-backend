"""add models[] + extra_headers{} to ai_providers

Kilo-Code-style custom provider: each provider can declare multiple model
variants (id + display name + reasoning flag) and inject arbitrary HTTP
headers into upstream requests. The legacy `model_id` column stays as the
default fallback for old callers and is auto-mirrored into `models[0]`.

Revision ID: 010_models_headers
Revises: 009_routing_policy
Create Date: 2026-05-14 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010_models_headers"
down_revision: Union[str, None] = "009_routing_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_providers",
        sa.Column(
            "models",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "ai_providers",
        sa.Column(
            "extra_headers",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    # Backfill models[] from legacy model_id (cross-dialect: build JSON via SQL)
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, model_id, display_name FROM ai_providers")).fetchall()
    for row in rows:
        model_id = (row[1] or "").strip()
        if not model_id:
            continue
        spec = [{"id": model_id, "name": row[2] or model_id, "reasoning": False}]
        bind.execute(
            sa.text("UPDATE ai_providers SET models = :m WHERE id = :i"),
            {"m": __import__("json").dumps(spec), "i": row[0]},
        )


def downgrade() -> None:
    op.drop_column("ai_providers", "extra_headers")
    op.drop_column("ai_providers", "models")
