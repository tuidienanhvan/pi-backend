"""rename agency tier to max and add subscription columns

Revision ID: 008
Revises: 007b_tenants_multi
Create Date: 2026-04-29 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007b_tenants_multi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _constraint_exists(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    checks = inspector.get_check_constraints(table_name)
    uniques = inspector.get_unique_constraints(table_name)
    return constraint_name in {c.get("name") for c in checks + uniques}


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _drop_tenant_tier_constraint(inspector: sa.Inspector) -> None:
    if _constraint_exists(inspector, "tenants", "ck_tenants_tier"):
        op.drop_constraint("ck_tenants_tier", "tenants", type_="check")


def _create_tenant_tier_constraint() -> None:
    op.create_check_constraint(
        "ck_tenants_tier",
        "tenants",
        "tier IN ('free', 'pro', 'max', 'enterprise')",
    )


def _create_legacy_tenant_tier_constraint() -> None:
    op.create_check_constraint(
        "ck_tenants_tier",
        "tenants",
        "tier IN ('free', 'pro', 'agency', 'enterprise')",
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # If an installation used a PostgreSQL enum type, rename the enum label
    # atomically. The current project migrations use VARCHAR + CHECK, so this
    # block is best-effort and harmless when the type does not exist.
    if _is_postgresql():
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tier_enum') THEN
                    ALTER TYPE tier_enum RENAME VALUE 'agency' TO 'max';
                END IF;
            EXCEPTION WHEN duplicate_object THEN
                NULL;
            END $$;
            """
        )

    if _table_exists(inspector, "tenants"):
        _drop_tenant_tier_constraint(inspector)
        op.execute("UPDATE tenants SET tier = 'max' WHERE tier = 'agency'")
        _create_tenant_tier_constraint()

        if not _column_exists(inspector, "tenants", "stripe_subscription_id"):
            op.add_column("tenants", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
        inspector = sa.inspect(bind)
        if not _constraint_exists(inspector, "tenants", "uq_tenant_stripe_sub"):
            op.create_unique_constraint("uq_tenant_stripe_sub", "tenants", ["stripe_subscription_id"])
        inspector = sa.inspect(bind)
        if not _column_exists(inspector, "tenants", "subscription_status"):
            op.add_column("tenants", sa.Column("subscription_status", sa.String(50), nullable=True))
        inspector = sa.inspect(bind)
        if not _column_exists(inspector, "tenants", "subscription_current_period_end"):
            op.add_column("tenants", sa.Column("subscription_current_period_end", sa.DateTime(timezone=True), nullable=True))

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "licenses"):
        op.execute("UPDATE licenses SET tier = 'max' WHERE tier = 'agency'")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "licenses"):
        op.execute("UPDATE licenses SET tier = 'agency' WHERE tier = 'max'")

    if _table_exists(inspector, "tenants"):
        if _constraint_exists(inspector, "tenants", "uq_tenant_stripe_sub"):
            op.drop_constraint("uq_tenant_stripe_sub", "tenants", type_="unique")
        inspector = sa.inspect(bind)
        for column in (
            "subscription_current_period_end",
            "subscription_status",
            "stripe_subscription_id",
        ):
            if _column_exists(inspector, "tenants", column):
                op.drop_column("tenants", column)
                inspector = sa.inspect(bind)

        _drop_tenant_tier_constraint(inspector)
        op.execute("UPDATE tenants SET tier = 'agency' WHERE tier = 'max'")
        _create_legacy_tenant_tier_constraint()

    if _is_postgresql():
        # PostgreSQL cannot reliably rename the enum label back after values may
        # have been created by newer app versions without coordinating deploys.
        # Existing project migrations use VARCHAR + CHECK, so this is documented
        # instead of attempting a risky enum rewrite.
        pass
