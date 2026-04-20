"""Admin service — aggregations + CRUD for Pi team dashboard."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import AppSetting
from app.admin.schemas import (
    AdminLicenseItem,
    AdminOverviewResponse,
    AdminProviderItem,
    AdminUsageRow,
    AdminUserItem,
    BrandingSettings,
    FeatureFlags,
    TokenPack,
)
from app.pi_ai_cloud.models import AiProvider, AiProviderKey, AiUsage, TokenWallet
from app.shared.auth.models import User
from app.shared.license.models import License, Site


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Overview ─────────────────────────────────────────
    async def overview(self) -> AdminOverviewResponse:
        since = datetime.now(timezone.utc) - timedelta(days=30)

        tokens_q = select(func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0)).where(
            AiUsage.created_at >= since, AiUsage.status == "success"
        )
        tokens_spent = int((await self.db.execute(tokens_q)).scalar_one())

        cost_q = select(func.coalesce(func.sum(AiUsage.upstream_cost_cents), 0)).where(
            AiUsage.created_at >= since, AiUsage.status == "success"
        )
        upstream_cost = int((await self.db.execute(cost_q)).scalar_one())

        # Revenue estimate — tokens × $9 per 100k
        revenue_cents = int(tokens_spent * 9 / 100_000 * 100)
        margin = 1 - (upstream_cost / revenue_cents) if revenue_cents > 0 else 0.0

        active_lic_q = select(func.count(License.id)).where(License.status == "active")
        active_licenses = int((await self.db.execute(active_lic_q)).scalar_one())

        # Provider health
        total_providers_q = select(func.count(AiProvider.id))
        healthy_q = select(func.count(AiProvider.id)).where(AiProvider.health_status == "healthy")
        down_q = select(func.count(AiProvider.id)).where(AiProvider.health_status == "down")

        total_providers = int((await self.db.execute(total_providers_q)).scalar_one())
        healthy = int((await self.db.execute(healthy_q)).scalar_one())
        down = int((await self.db.execute(down_q)).scalar_one())

        # Top plugins
        top_q = (
            select(AiUsage.source_plugin, func.count(AiUsage.id).label("calls"))
            .where(AiUsage.created_at >= since, AiUsage.source_plugin != "")
            .group_by(AiUsage.source_plugin)
            .order_by(desc("calls"))
            .limit(5)
        )
        top = [{"plugin": r[0], "calls": int(r[1])} for r in (await self.db.execute(top_q)).all()]

        return AdminOverviewResponse(
            revenue_30d=revenue_cents / 100.0,
            upstream_cost_30d=upstream_cost / 100.0,
            margin_pct=round(margin, 3),
            active_licenses=active_licenses,
            tokens_spent_30d=tokens_spent,
            total_providers=total_providers,
            healthy_providers=healthy,
            down_providers=down,
            top_plugins=top,
        )

    # ─── Licenses ─────────────────────────────────────────
    async def list_licenses(
        self,
        *,
        q: str = "",
        tier: str = "",
        status: str = "",
        plugin: str = "",
        package: str = "",
        expires_in: str = "",  # '7d'|'30d'|'90d'|'expired'
        sort: str = "-created_at",  # e.g. '-created_at', 'expires_at', '-quota_used'
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AdminLicenseItem], int, dict]:
        from app.admin.schemas import AdminLicenseItem
        from app.pi_ai_cloud.models import AiPackage, AiProviderKey, LicensePackage

        now = datetime.now(timezone.utc)

        # Base query for listing (with filters)
        query = select(License)
        if q:
            like = f"%{q}%"
            query = query.where(
                (License.email.ilike(like))
                | (License.key.ilike(like))
                | (License.customer_name.ilike(like))
            )
        if tier:
            query = query.where(License.tier == tier)
        if status:
            query = query.where(License.status == status)
        if plugin:
            query = query.where(License.plugin == plugin)
        if expires_in:
            if expires_in == "expired":
                query = query.where(License.expires_at < now)
            elif expires_in == "7d":
                query = query.where(License.expires_at.between(now, now + timedelta(days=7)))
            elif expires_in == "30d":
                query = query.where(License.expires_at.between(now, now + timedelta(days=30)))
            elif expires_in == "90d":
                query = query.where(License.expires_at.between(now, now + timedelta(days=90)))
        if package:
            # Join LicensePackage to filter by package_slug
            query = query.join(LicensePackage, LicensePackage.license_id == License.id).where(
                LicensePackage.package_slug == package
            )

        # Total (before limit/offset)
        total_q = select(func.count()).select_from(query.subquery())
        total = int((await self.db.execute(total_q)).scalar_one())

        # Sort
        sort_map = {
            "created_at": License.created_at,
            "expires_at": License.expires_at,
            "id": License.id,
        }
        sort_key = sort.lstrip("-")
        col = sort_map.get(sort_key, License.created_at)
        query = query.order_by(col.desc() if sort.startswith("-") else col.asc())
        query = query.limit(limit).offset(offset)
        licenses = list((await self.db.execute(query)).scalars().all())

        # Bulk fetch: sites count, package state, keys count per license
        license_ids = [lic.id for lic in licenses]
        sites_counts: dict[int, int] = {}
        packages_map: dict[int, tuple] = {}  # license_id -> (lp, ap)
        keys_counts: dict[int, int] = {}

        if license_ids:
            # Sites
            sq = (
                select(Site.license_id, func.count(Site.id))
                .where(Site.license_id.in_(license_ids), Site.is_active.is_(True))
                .group_by(Site.license_id)
            )
            sites_counts = dict((await self.db.execute(sq)).all())

            # Packages + package metadata
            pq = (
                select(LicensePackage, AiPackage)
                .join(AiPackage, AiPackage.slug == LicensePackage.package_slug)
                .where(LicensePackage.license_id.in_(license_ids))
            )
            for lp, ap in (await self.db.execute(pq)).all():
                packages_map[lp.license_id] = (lp, ap)

            # Allocated keys count
            kq = (
                select(AiProviderKey.allocated_to_license_id, func.count(AiProviderKey.id))
                .where(AiProviderKey.allocated_to_license_id.in_(license_ids))
                .group_by(AiProviderKey.allocated_to_license_id)
            )
            keys_counts = dict((await self.db.execute(kq)).all())

        # Build items
        items: list[AdminLicenseItem] = []
        for lic in licenses:
            pkg_slug = pkg_name = None
            quota_used = quota_limit = 0
            quota_pct = 0.0
            if lic.id in packages_map:
                lp, ap = packages_map[lic.id]
                pkg_slug = ap.slug
                pkg_name = ap.display_name
                quota_used = int(lp.current_period_tokens_used or 0)
                quota_limit = int(ap.token_quota_monthly or 0)
                quota_pct = (quota_used / quota_limit * 100) if quota_limit > 0 else 0.0

            items.append(AdminLicenseItem(
                id=lic.id,
                key=lic.key,
                email=lic.email,
                name=lic.customer_name or "",
                plugin=lic.plugin,
                tier=lic.tier,
                status=lic.status,
                max_sites=lic.max_sites,
                activated_sites=int(sites_counts.get(lic.id, 0)),
                expires_at=lic.expires_at,
                created_at=lic.created_at,
                package_slug=pkg_slug,
                package_name=pkg_name,
                quota_used=quota_used,
                quota_limit=quota_limit,
                quota_pct=round(quota_pct, 2),
                allocated_keys_count=int(keys_counts.get(lic.id, 0)),
                last_active_at=None,
            ))

        # Facets (ignore current filters for facet counts so users see full picture)
        facets = await self._license_facets()

        return items, total, facets

    async def _license_facets(self) -> dict:
        """Aggregate counts for filter dropdown badges."""
        from app.pi_ai_cloud.models import LicensePackage

        # status
        sq = select(License.status, func.count(License.id)).group_by(License.status)
        by_status = {k: int(v) for k, v in (await self.db.execute(sq)).all() if k}
        # tier
        tq = select(License.tier, func.count(License.id)).group_by(License.tier)
        by_tier = {k: int(v) for k, v in (await self.db.execute(tq)).all() if k}
        # plugin
        pq = select(License.plugin, func.count(License.id)).group_by(License.plugin)
        by_plugin = {k: int(v) for k, v in (await self.db.execute(pq)).all() if k}
        # package
        kq = (
            select(LicensePackage.package_slug, func.count(LicensePackage.license_id))
            .group_by(LicensePackage.package_slug)
        )
        by_package = {k: int(v) for k, v in (await self.db.execute(kq)).all() if k}

        return {
            "by_status": by_status,
            "by_tier": by_tier,
            "by_plugin": by_plugin,
            "by_package": by_package,
        }

    async def create_license(self, payload) -> License:
        lic = License.new(
            plugin=payload.plugin,
            email=payload.email,
            tier=payload.tier,
            max_sites=payload.max_sites,
            customer_name=payload.name,
        )
        if payload.expires_days > 0:
            lic.expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_days)
        if payload.notes:
            lic.notes = payload.notes
        self.db.add(lic)
        await self.db.flush()
        return lic

    async def patch_license(self, license_id: int, payload) -> License | None:
        lic = await self.db.get(License, license_id)
        if lic is None:
            return None
        for field in ("tier", "max_sites", "expires_at", "status", "notes"):
            val = getattr(payload, field, None)
            if val is not None:
                setattr(lic, field, val)
        await self.db.flush()
        return lic

    async def revoke_license(self, license_id: int) -> bool:
        lic = await self.db.get(License, license_id)
        if lic is None:
            return False
        lic.status = "revoked"
        await self.db.flush()
        return True

    # ─── Users ────────────────────────────────────────────
    async def list_users(self, q: str = "", limit: int = 50, offset: int = 0) -> tuple[list[AdminUserItem], int]:
        query = select(User)
        if q:
            like = f"%{q}%"
            query = query.where((User.email.ilike(like)) | (User.name.ilike(like)))

        total_q = select(func.count()).select_from(query.subquery())
        total = int((await self.db.execute(total_q)).scalar_one())

        query = query.order_by(User.id.desc()).limit(limit).offset(offset)
        users = list((await self.db.execute(query)).scalars().all())

        items: list[AdminUserItem] = []
        for u in users:
            lic_count_q = select(func.count(License.id)).where(License.email == u.email)
            lic_count = int((await self.db.execute(lic_count_q)).scalar_one())

            balance_q = (
                select(func.coalesce(func.sum(TokenWallet.balance), 0))
                .join(License, License.id == TokenWallet.license_id)
                .where(License.email == u.email)
            )
            balance = int((await self.db.execute(balance_q)).scalar_one())

            spent_q = (
                select(func.coalesce(func.sum(TokenWallet.lifetime_topup), 0))
                .join(License, License.id == TokenWallet.license_id)
                .where(License.email == u.email)
            )
            # 9 cents per 100 tokens (approximately, depending on pack)
            lifetime_topup = int((await self.db.execute(spent_q)).scalar_one())
            spent_cents = int(lifetime_topup * 9 / 100_000 * 100)

            items.append(AdminUserItem(
                id=u.id,
                email=u.email,
                name=u.name,
                is_admin=u.is_admin,
                is_verified=u.is_verified,
                license_count=lic_count,
                token_balance=balance,
                total_spent_cents=spent_cents,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            ))
        return items, total

    # ─── Providers ────────────────────────────────────────
    async def _provider_to_item(self, p: AiProvider) -> AdminProviderItem:
        # Aggregate pool stats
        counts_q = (
            select(AiProviderKey.status, func.count(AiProviderKey.id))
            .where(AiProviderKey.provider_id == p.id)
            .group_by(AiProviderKey.status)
        )
        counts = dict((await self.db.execute(counts_q)).all())
        keys_total = sum(int(v) for v in counts.values())
        return AdminProviderItem(
            id=p.id, slug=p.slug, display_name=p.display_name, adapter=p.adapter,
            base_url=p.base_url, model_id=p.model_id, tier=p.tier, priority=p.priority,
            is_enabled=p.is_enabled, health_status=p.health_status,
            input_cost_per_mtok_cents=p.input_cost_per_mtok_cents,
            output_cost_per_mtok_cents=p.output_cost_per_mtok_cents,
            pi_tokens_per_input=p.pi_tokens_per_input,
            pi_tokens_per_output=p.pi_tokens_per_output,
            consecutive_failures=p.consecutive_failures,
            last_error=p.last_error or "",
            last_success_at=p.last_success_at,
            keys_total=keys_total,
            keys_available=int(counts.get("available", 0)),
            keys_allocated=int(counts.get("allocated", 0)),
            has_api_key=keys_total > 0,
        )

    async def list_providers(self) -> list[AdminProviderItem]:
        q = select(AiProvider).order_by(AiProvider.priority.asc())
        rows = (await self.db.execute(q)).scalars().all()
        return [await self._provider_to_item(p) for p in rows]

    async def patch_provider(self, provider_id: int, payload) -> AiProvider | None:
        p = await self.db.get(AiProvider, provider_id)
        if p is None:
            return None
        # api_key is handled separately (deposited into pool if provided)
        api_key_val = getattr(payload, "api_key", None)
        for field in (
            "display_name", "adapter", "base_url", "model_id",
            "is_enabled", "priority", "tier",
            "input_cost_per_mtok_cents", "output_cost_per_mtok_cents",
            "pi_tokens_per_input", "pi_tokens_per_output",
        ):
            val = getattr(payload, field, None)
            if val is not None:
                setattr(p, field, val)
        await self.db.flush()

        # Back-compat: if admin typed an api_key in old UI, drop it into the pool
        if api_key_val:
            self.db.add(AiProviderKey(
                provider_id=p.id, key_value=api_key_val.strip(),
                label="legacy-from-provider-edit", status="available",
            ))
            await self.db.flush()
        return p

    async def create_provider(self, payload) -> AiProvider:
        p = AiProvider(
            slug=payload.slug.strip(),
            display_name=payload.display_name.strip(),
            adapter=payload.adapter,
            base_url=payload.base_url.strip(),
            model_id=payload.model_id.strip(),
            tier=payload.tier,
            priority=payload.priority,
            input_cost_per_mtok_cents=payload.input_cost_per_mtok_cents,
            output_cost_per_mtok_cents=payload.output_cost_per_mtok_cents,
            pi_tokens_per_input=payload.pi_tokens_per_input,
            pi_tokens_per_output=payload.pi_tokens_per_output,
            is_enabled=payload.is_enabled,
            health_status="healthy",
        )
        self.db.add(p)
        await self.db.flush()
        # If admin provided an api_key on create, seed 1 key into the pool
        if getattr(payload, "api_key", None):
            self.db.add(AiProviderKey(
                provider_id=p.id, key_value=payload.api_key.strip(),
                label="seed-on-create", status="available",
            ))
            await self.db.flush()
        return p

    async def delete_provider(self, provider_id: int) -> bool:
        p = await self.db.get(AiProvider, provider_id)
        if p is None:
            return False
        await self.db.delete(p)
        await self.db.flush()
        return True

    # ─── Settings (key-value store) ───────────────────────
    DEFAULT_BRANDING = BrandingSettings().model_dump()
    DEFAULT_PACKS = [
        TokenPack(slug="starter", tokens=10_000, price_cents=100, discount_pct=0, label="Starter").model_dump(),
        TokenPack(slug="standard", tokens=100_000, price_cents=900, discount_pct=10, label="Standard").model_dump(),
        TokenPack(slug="pro", tokens=500_000, price_cents=3500, discount_pct=30, label="Pro").model_dump(),
        TokenPack(slug="agency", tokens=1_000_000, price_cents=5900, discount_pct=41, label="Agency").model_dump(),
        TokenPack(slug="enterprise", tokens=5_000_000, price_cents=24900, discount_pct=50, label="Enterprise").model_dump(),
    ]
    DEFAULT_FLAGS = FeatureFlags().model_dump()

    async def _get_setting(self, key: str, default: Any) -> Any:
        row = await self.db.get(AppSetting, key)
        return row.value if row else default

    async def _set_setting(self, key: str, value: Any) -> None:
        row = await self.db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value)
            self.db.add(row)
        else:
            row.value = value
        await self.db.flush()

    async def get_settings(self) -> dict[str, Any]:
        branding = await self._get_setting("branding", self.DEFAULT_BRANDING)
        packs = await self._get_setting("token_packs", self.DEFAULT_PACKS)
        flags = await self._get_setting("feature_flags", self.DEFAULT_FLAGS)
        return {"branding": branding, "token_packs": packs, "feature_flags": flags}

    async def update_settings(self, payload) -> dict[str, Any]:
        if payload.branding is not None:
            await self._set_setting("branding", payload.branding.model_dump())
        if payload.token_packs is not None:
            await self._set_setting("token_packs", [p.model_dump() for p in payload.token_packs])
        if payload.feature_flags is not None:
            await self._set_setting("feature_flags", payload.feature_flags.model_dump())
        return await self.get_settings()

    # ─── Usage ────────────────────────────────────────────
    async def usage(
        self, *, days: int = 30, plugin: str = "", quality: str = "", status: str = "",
    ) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        conditions = [AiUsage.created_at >= since]
        if status:
            conditions.append(AiUsage.status == status)
        else:
            conditions.append(AiUsage.status == "success")
        if plugin:
            conditions.append(AiUsage.source_plugin == plugin)
        # quality filter: joins to AiProvider.tier — 'fast'=free, 'best'=paid, 'balanced'=both
        # Skipping for now; AiUsage doesn't track quality directly. Left as no-op.
        _ = quality
        where_ok = and_(*conditions)

        total_calls = int((await self.db.execute(
            select(func.count(AiUsage.id)).where(where_ok)
        )).scalar_one())
        tokens_spent = int((await self.db.execute(
            select(func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0)).where(where_ok)
        )).scalar_one())
        upstream_cost = int((await self.db.execute(
            select(func.coalesce(func.sum(AiUsage.upstream_cost_cents), 0)).where(where_ok)
        )).scalar_one())
        avg_latency = int((await self.db.execute(
            select(func.coalesce(func.avg(AiUsage.latency_ms), 0)).where(where_ok)
        )).scalar_one())

        by_plugin_q = (
            select(
                AiUsage.source_plugin,
                func.count(AiUsage.id),
                func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0),
                func.coalesce(func.sum(AiUsage.upstream_cost_cents), 0),
            )
            .where(where_ok)
            .group_by(AiUsage.source_plugin)
            .order_by(desc(func.sum(AiUsage.pi_tokens_charged)))
        )
        rows: list[AdminUsageRow] = []
        for plugin, calls, tokens, cost_cents in (await self.db.execute(by_plugin_q)).all():
            revenue = tokens * 9 / 100_000
            margin = 1 - (cost_cents / 100.0 / revenue) if revenue > 0 else 0.0
            rows.append(AdminUsageRow(
                plugin=plugin or "direct",
                calls=int(calls),
                tokens=int(tokens),
                revenue_usd=round(revenue, 2),
                upstream_usd=round(cost_cents / 100.0, 4),
                margin_pct=round(margin, 3),
            ))

        # ─── Daily breakdown (success + failed separately) ──────
        base_conditions = [AiUsage.created_at >= since]
        if plugin:
            base_conditions.append(AiUsage.source_plugin == plugin)

        daily_q = (
            select(
                func.date_trunc("day", AiUsage.created_at).label("day"),
                AiUsage.status,
                func.count(AiUsage.id).label("calls"),
                func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0).label("tokens"),
            )
            .where(and_(*base_conditions))
            .group_by("day", AiUsage.status)
            .order_by("day")
        )
        daily_map: dict = {}  # date_iso -> {success, fail, tokens}
        for row in (await self.db.execute(daily_q)).all():
            day_iso = row.day.date().isoformat() if row.day else None
            if not day_iso:
                continue
            entry = daily_map.setdefault(day_iso, {"date": day_iso, "success": 0, "fail": 0, "tokens": 0})
            if row.status == "success":
                entry["success"] = int(row.calls)
            else:
                entry["fail"] += int(row.calls)
            entry["tokens"] += int(row.tokens)

        # Fill gaps so chart has one bar per day even when idle
        daily: list[dict] = []
        today = datetime.now(timezone.utc).date()
        for i in range(days):
            d = (today - timedelta(days=days - 1 - i)).isoformat()
            daily.append(daily_map.get(d, {"date": d, "success": 0, "fail": 0, "tokens": 0}))

        # ─── Error breakdown (top 10 by count, among failed) ────
        error_conditions = [AiUsage.created_at >= since, AiUsage.status != "success"]
        if plugin:
            error_conditions.append(AiUsage.source_plugin == plugin)

        errors_q = (
            select(
                AiUsage.error_code,
                func.count(AiUsage.id).label("count"),
            )
            .where(and_(*error_conditions))
            .group_by(AiUsage.error_code)
            .order_by(desc(func.count(AiUsage.id)))
            .limit(10)
        )
        errors: list[dict] = []
        for ec, count in (await self.db.execute(errors_q)).all():
            errors.append({"code": ec or "unknown", "count": int(count), "sample": ""})

        return {
            "total_calls": total_calls,
            "tokens_spent": tokens_spent,
            "upstream_cost_cents": upstream_cost,
            "avg_latency_ms": avg_latency,
            "by_plugin": rows,
            "daily": daily,
            "errors": errors,
        }

    # ─── Revenue ──────────────────────────────────────────
    async def revenue(self, days: int = 30) -> dict:
        """Simple revenue calc from wallet top-ups + license creation.

        Real impl would read from billing table; for now, aggregate from
        AiUsage (tokens × price) + PaidLicense count × their one-time fee.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        tokens_q = select(func.coalesce(func.sum(AiUsage.pi_tokens_charged), 0)).where(
            AiUsage.created_at >= since, AiUsage.status == "success"
        )
        tokens = int((await self.db.execute(tokens_q)).scalar_one())
        cost_q = select(func.coalesce(func.sum(AiUsage.upstream_cost_cents), 0)).where(
            AiUsage.created_at >= since, AiUsage.status == "success"
        )
        cost_cents = int((await self.db.execute(cost_q)).scalar_one())
        revenue_cents = int(tokens * 9 / 100_000 * 100)
        margin = 1 - (cost_cents / revenue_cents) if revenue_cents > 0 else 0.0

        return {
            "revenue_cents": revenue_cents,
            "cost_cents": cost_cents,
            "margin_pct": round(margin, 3),
            "by_product": [
                {"sku": "pi-ai-tokens", "name": "Pi AI Cloud tokens", "type": "usage", "count": tokens, "revenue_cents": revenue_cents},
            ],
        }
