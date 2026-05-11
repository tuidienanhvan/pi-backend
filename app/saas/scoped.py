"""Helpers for tenant-scoped SQLAlchemy queries."""

from typing import TypeVar

from sqlalchemy import Select

from app.saas.deps import TenantContext

T = TypeVar("T")


def scoped_query(stmt: Select[tuple[T]], ctx: TenantContext, model: type) -> Select[tuple[T]]:
    """Append `model.tenant_id == ctx.tenant_id` when the model supports it."""
    tenant_col = getattr(model, "tenant_id", None)
    if tenant_col is None:
        return stmt
    return stmt.where(tenant_col == ctx.tenant_id)

