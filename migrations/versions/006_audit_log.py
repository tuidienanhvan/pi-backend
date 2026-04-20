"""audit_log table — every admin mutation recorded

Revision ID: 006_audit_log
Revises: 005_key_pool
Create Date: 2026-04-18 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_audit_log"
down_revision: Union[str, None] = "005_key_pool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        # Actor (admin user who did the thing)
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("actor_email", sa.String(255), nullable=False, server_default=""),
        # Action verb: create | update | delete | revoke | reactivate | allocate | assign | login | logout
        sa.Column("action", sa.String(32), nullable=False, index=True),
        # Resource affected
        sa.Column("resource_type", sa.String(32), nullable=False, index=True),
        # license | key | package | provider | user | release | settings | auth
        sa.Column("resource_id", sa.String(64), nullable=False, server_default="", index=True),
        sa.Column("resource_label", sa.String(255), nullable=False, server_default=""),
        # Diff — before/after JSON snapshot
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        # Request context
        sa.Column("ip_address", sa.String(64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(500), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(64), nullable=False, server_default=""),
        # Human-readable message
        sa.Column("message", sa.String(500), nullable=False, server_default=""),
        # Severity: info | warning | critical
        sa.Column("severity", sa.String(16), nullable=False, server_default="info", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )
    # Composite for common queries
    op.create_index(
        "ix_audit_log_resource",
        "audit_log",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_resource", table_name="audit_log")
    op.drop_table("audit_log")
