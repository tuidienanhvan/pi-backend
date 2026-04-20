"""License service — CRUD + site activation + domain matching."""

from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.license.models import License, Site
from app.shared.usage import UsageLog


class LicenseService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Queries ─────────────────────────────────────────
    async def get_by_key(self, key: str) -> License | None:
        q = select(License).where(License.key == key)
        result = await self.db.execute(q)
        return result.scalar_one_or_none()

    async def activated_sites_count(self, lic: License) -> int:
        q = select(func.count(Site.id)).where(
            Site.license_id == lic.id, Site.is_active.is_(True)
        )
        result = await self.db.execute(q)
        return int(result.scalar_one())

    async def site_is_activated(self, lic: License, site_url: str) -> bool:
        domain = self._normalise_domain(site_url)
        q = select(Site).where(
            Site.license_id == lic.id,
            Site.domain == domain,
            Site.is_active.is_(True),
        )
        result = await self.db.execute(q)
        return result.scalar_one_or_none() is not None

    async def usage_this_month(self, lic: License) -> int:
        """Count UsageLog rows for this license, current calendar month, success only."""
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        q = select(func.count(UsageLog.id)).where(
            UsageLog.license_id == lic.id,
            UsageLog.created_at >= start,
            UsageLog.status == "success",
        )
        result = await self.db.execute(q)
        return int(result.scalar_one())

    # ─── Mutations ───────────────────────────────────────
    async def activate_site(
        self,
        lic: License,
        site_url: str,
        plugin_version: str = "",
        wp_version: str = "",
        php_version: str = "",
    ) -> tuple[Site, bool]:
        """Activate `site_url` for this license.

        Returns (Site, created) — created=True if new record, False if existing.
        Raises ValueError if max_sites exceeded.
        """
        domain = self._normalise_domain(site_url)

        # Check existing
        q = select(Site).where(Site.license_id == lic.id, Site.domain == domain)
        result = await self.db.execute(q)
        existing = result.scalar_one_or_none()

        if existing is not None:
            # Reactivate + bump metadata
            existing.is_active = True
            existing.plugin_version = plugin_version
            existing.wp_version = wp_version
            existing.php_version = php_version
            existing.last_seen_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing, False

        # Check limit before creating
        current = await self.activated_sites_count(lic)
        if current >= lic.max_sites:
            raise ValueError(
                f"Max sites ({lic.max_sites}) reached. Deactivate another site first."
            )

        site = Site(
            license_id=lic.id,
            domain=domain,
            plugin_version=plugin_version,
            wp_version=wp_version,
            php_version=php_version,
            last_seen_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.db.add(site)
        await self.db.flush()
        return site, True

    async def deactivate_site(self, lic: License, site_url: str) -> bool:
        domain = self._normalise_domain(site_url)
        q = select(Site).where(Site.license_id == lic.id, Site.domain == domain)
        result = await self.db.execute(q)
        site = result.scalar_one_or_none()
        if site is None:
            return False
        site.is_active = False
        await self.db.flush()
        return True

    async def log_usage(
        self,
        lic: License,
        endpoint: str,
        *,
        site_domain: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        cost_cents: int = 0,
        status: str = "success",
        latency_ms: int = 0,
        error_message: str = "",
    ) -> UsageLog:
        log = UsageLog(
            license_id=lic.id,
            endpoint=endpoint,
            site_domain=site_domain,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_cents=cost_cents,
            status=status,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        self.db.add(log)
        await self.db.flush()
        return log

    # ─── Helpers ─────────────────────────────────────────
    @staticmethod
    def _normalise_domain(site_url: str) -> str:
        """Extract hostname from URL, lowercase, strip www."""
        if not site_url.startswith(("http://", "https://")):
            site_url = "https://" + site_url
        host = urlparse(site_url).hostname or ""
        host = host.lower().strip()
        return host.removeprefix("www.")
