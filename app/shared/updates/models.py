"""PluginRelease — stores downloadable plugin ZIP versions (update server)."""

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class PluginRelease(Base, TimestampMixin):
    __tablename__ = "plugin_releases"
    __table_args__ = (
        UniqueConstraint("plugin_slug", "version", name="uq_plugin_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    plugin_slug: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # e.g. "pi-seo", "pi-dashboard", "pi-analytics"

    version: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # Semver: "1.3.0"

    tier_required: Mapped[str] = mapped_column(String(16), default="free")
    # "free" = anyone can download; "pro"/"agency" = license tier gate

    zip_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # Relative path under UPDATES_STORAGE_PATH

    zip_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    zip_sha256: Mapped[str] = mapped_column(String(64), default="")

    changelog: Mapped[str] = mapped_column(Text, default="")
    is_stable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_yanked: Mapped[bool] = mapped_column(Boolean, default=False)
    # If yanked, plugin won't advertise this version for update

    min_php_version: Mapped[str] = mapped_column(String(8), default="8.3")
    min_wp_version: Mapped[str] = mapped_column(String(8), default="6.0")
