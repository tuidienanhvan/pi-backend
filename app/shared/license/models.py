"""License + Site models — core auth for Pi plugins."""

import secrets
from datetime import datetime
from typing import Literal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin

LicenseTier = Literal["free", "pro", "agency"]
LicenseStatus = Literal["active", "expired", "revoked", "suspended"]


def _gen_key(prefix: str = "pi_") -> str:
    """Generate a random license key — 32 hex chars after prefix."""
    return prefix + secrets.token_hex(16)


class License(Base, TimestampMixin):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    plugin: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # e.g. "pi-seo-pro", "pi-dashboard-pro", "pi-analytics-pro"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), default="")

    tier: Mapped[str] = mapped_column(String(16), default="free", index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)

    max_sites: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stripe / payment references (optional)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notes: Mapped[str] = mapped_column(String(1000), default="")

    sites: Mapped[list["Site"]] = relationship(
        back_populates="license", cascade="all, delete-orphan"
    )

    @classmethod
    def new(
        cls,
        *,
        plugin: str,
        email: str,
        tier: LicenseTier = "free",
        max_sites: int = 1,
        customer_name: str = "",
        key_prefix: str = "pi_",
    ) -> "License":
        return cls(
            key=_gen_key(key_prefix),
            plugin=plugin,
            email=email,
            tier=tier,
            max_sites=max_sites,
            customer_name=customer_name,
            status="active",
        )

    @property
    def is_active(self) -> bool:
        if self.status != "active":
            return False
        if self.expires_at is not None:
            # Compare naive-aware safely
            from datetime import timezone

            now = datetime.now(timezone.utc)
            exp = self.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
        return True


class Site(Base, TimestampMixin):
    """A WordPress site that's activated this license."""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("license_id", "domain", name="uq_site_license_domain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )

    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # Plugin metadata for support
    wp_version: Mapped[str] = mapped_column(String(32), default="")
    php_version: Mapped[str] = mapped_column(String(32), default="")
    plugin_version: Mapped[str] = mapped_column(String(32), default="")

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    license: Mapped["License"] = relationship(back_populates="sites")
