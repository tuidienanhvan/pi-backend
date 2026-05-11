"""Central ORM model registry — Alembic + test fixtures import from here.

Each plugin defines its own models in its package; this file just re-exports
so that `Base.metadata` sees every table for autogenerate.
"""

from app.admin.audit import AuditLog
from app.admin.models import AppSetting
from app.core.base import Base
from app.pi_ai_cloud.models import (
    AiPackage,
    AiProvider,
    AiProviderKey,
    AiUsage,
    LicensePackage,
    TokenLedger,
    TokenWallet,
)
from app.shared.auth.models import User
from app.shared.license.models import License, Site
from app.shared.updates.models import PluginRelease
from app.shared.usage import UsageLog
from app.saas.models import AdminAuditLog, Tenant, Token, TokenTransaction

__all__ = [
    "AdminAuditLog",
    "AiPackage",
    "AiProvider",
    "AiProviderKey",
    "AiUsage",
    "AppSetting",
    "AuditLog",
    "Base",
    "License",
    "LicensePackage",
    "PluginRelease",
    "Site",
    "Tenant",
    "Token",
    "TokenTransaction",
    "TokenLedger",
    "TokenWallet",
    "UsageLog",
    "User",
]
