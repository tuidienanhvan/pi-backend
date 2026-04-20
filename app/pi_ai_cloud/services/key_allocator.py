"""KeyAllocator — manages the pool of upstream AI keys.

Each customer (license) gets N keys allocated from the pool. Customer's
router uses ONLY those keys. Admin can:
  - bulk-allocate: "give license #42 three groq + two gemini keys"
  - manual-allocate: pick specific keys from pool
  - revoke: move a key back to the pool
  - reset-period: called by cron on the 1st of each month

Keys are never shared between customers.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.pi_ai_cloud.models import AiProvider, AiProviderKey


class KeyAllocator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Pool queries ──────────────────────────────────────
    async def pool_summary(self) -> list[dict]:
        """Return available/allocated counts per provider."""
        q = (
            select(
                AiProvider.id,
                AiProvider.slug,
                AiProvider.display_name,
                AiProviderKey.status,
                func.count(AiProviderKey.id),
            )
            .join(AiProviderKey, AiProviderKey.provider_id == AiProvider.id, isouter=True)
            .group_by(AiProvider.id, AiProvider.slug, AiProvider.display_name, AiProviderKey.status)
            .order_by(AiProvider.priority.asc())
        )
        rows = (await self.db.execute(q)).all()
        acc: dict[int, dict] = {}
        for pid, slug, name, status, count in rows:
            if pid not in acc:
                acc[pid] = {
                    "provider_id": pid, "slug": slug, "display_name": name,
                    "available": 0, "allocated": 0, "exhausted": 0, "banned": 0, "total": 0,
                }
            if status:
                acc[pid][status] = int(count)
                acc[pid]["total"] += int(count)
        return list(acc.values())

    async def list_keys(
        self, *, provider_id: int | None = None, status: str | None = None,
        health_status: str | None = None, has_errors: bool | None = None,
        license_id: int | None = None, q: str = "", sort: str = "-id",
        limit: int = 200, offset: int = 0,
    ) -> tuple[list[AiProviderKey], int]:
        qry = select(AiProviderKey)
        if provider_id is not None:
            qry = qry.where(AiProviderKey.provider_id == provider_id)
        if status:
            qry = qry.where(AiProviderKey.status == status)
        if health_status:
            qry = qry.where(AiProviderKey.health_status == health_status)
        if has_errors:
            qry = qry.where(AiProviderKey.consecutive_failures > 0)
        if license_id is not None:
            qry = qry.where(AiProviderKey.allocated_to_license_id == license_id)
        if q:
            like = f"%{q}%"
            qry = qry.where(
                (AiProviderKey.label.ilike(like)) | (AiProviderKey.notes.ilike(like))
            )

        total = int((await self.db.execute(select(func.count()).select_from(qry.subquery()))).scalar_one())

        sort_map = {
            "id": AiProviderKey.id,
            "monthly_used_tokens": AiProviderKey.monthly_used_tokens,
            "consecutive_failures": AiProviderKey.consecutive_failures,
            "last_success_at": AiProviderKey.last_success_at,
        }
        key = sort.lstrip("-")
        col = sort_map.get(key, AiProviderKey.id)
        qry = qry.order_by(col.desc() if sort.startswith("-") else col.asc())
        qry = qry.limit(limit).offset(offset)
        items = list((await self.db.execute(qry)).scalars().all())
        return items, total

    # ─── Pool mutations (add / import) ─────────────────────
    async def add_key(
        self, *, provider_id: int, key_value: str, label: str = "",
        monthly_quota_tokens: int = 0, notes: str = "",
    ) -> AiProviderKey:
        k = AiProviderKey(
            provider_id=provider_id,
            key_value=key_value.strip(),
            label=label.strip(),
            status="available",
            monthly_quota_tokens=monthly_quota_tokens,
            notes=notes,
        )
        self.db.add(k)
        await self.db.flush()
        return k

    async def bulk_import(self, rows: Sequence[dict]) -> dict:
        """Rows: [{provider_id|provider_slug, key_value, label?, monthly_quota_tokens?}]."""
        # Resolve slug → id
        slugs = {r["provider_slug"] for r in rows if "provider_slug" in r}
        slug_map: dict[str, int] = {}
        if slugs:
            q = select(AiProvider.slug, AiProvider.id).where(AiProvider.slug.in_(slugs))
            slug_map = dict((await self.db.execute(q)).all())

        added, skipped, errors = 0, 0, []
        for r in rows:
            pid = r.get("provider_id") or slug_map.get(r.get("provider_slug", ""))
            key = (r.get("key_value") or "").strip()
            if not pid or not key:
                skipped += 1
                errors.append(f"Missing provider or key: {r!r}")
                continue
            self.db.add(AiProviderKey(
                provider_id=pid, key_value=key,
                label=r.get("label", ""), status="available",
                monthly_quota_tokens=r.get("monthly_quota_tokens", 0),
                notes=r.get("notes", ""),
            ))
            added += 1
        await self.db.flush()
        return {"added": added, "skipped": skipped, "errors": errors[:10]}

    async def delete_key(self, key_id: int) -> bool:
        k = await self.db.get(AiProviderKey, key_id)
        if k is None:
            return False
        await self.db.delete(k)
        await self.db.flush()
        return True

    # ─── Allocation ────────────────────────────────────────
    async def allocate_to_license(
        self, *, license_id: int, provider_id: int, count: int = 1
    ) -> list[AiProviderKey]:
        """Pick `count` available keys for provider and assign to license."""
        q = (
            select(AiProviderKey)
            .where(
                AiProviderKey.provider_id == provider_id,
                AiProviderKey.status == "available",
                AiProviderKey.allocated_to_license_id.is_(None),
            )
            .order_by(AiProviderKey.id.asc())
            .limit(count)
        )
        picks = list((await self.db.execute(q)).scalars().all())
        now = datetime.now(timezone.utc)
        for k in picks:
            k.status = "allocated"
            k.allocated_to_license_id = license_id
            k.allocated_at = now
        await self.db.flush()
        return picks

    async def allocate_specific(self, key_id: int, license_id: int) -> AiProviderKey | None:
        k = await self.db.get(AiProviderKey, key_id)
        if k is None:
            return None
        if k.status not in ("available", "allocated"):
            return None
        k.status = "allocated"
        k.allocated_to_license_id = license_id
        k.allocated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return k

    async def revoke_key(self, key_id: int) -> AiProviderKey | None:
        """Pull a key back to the available pool."""
        k = await self.db.get(AiProviderKey, key_id)
        if k is None:
            return None
        k.status = "available"
        k.allocated_to_license_id = None
        k.allocated_at = None
        await self.db.flush()
        return k

    async def revoke_all_for_license(self, license_id: int) -> int:
        res = await self.db.execute(
            update(AiProviderKey)
            .where(AiProviderKey.allocated_to_license_id == license_id)
            .values(status="available", allocated_to_license_id=None, allocated_at=None)
        )
        await self.db.flush()
        return res.rowcount or 0

    # ─── Router query: keys FOR a specific license ─────────
    async def keys_for_license(self, license_id: int) -> list[AiProviderKey]:
        """All allocated + healthy keys belonging to one customer."""
        q = (
            select(AiProviderKey)
            .where(
                AiProviderKey.allocated_to_license_id == license_id,
                AiProviderKey.status == "allocated",
                AiProviderKey.health_status != "down",
            )
            .order_by(AiProviderKey.monthly_used_tokens.asc())  # least-used first
        )
        return list((await self.db.execute(q)).scalars().all())

    # ─── Period / quota maintenance ────────────────────────
    async def reset_monthly_counters(self) -> int:
        """Cron: on 1st of month, reset per-key used-tokens and exhausted→active."""
        now = datetime.now(timezone.utc)
        res = await self.db.execute(
            update(AiProviderKey).values(
                monthly_used_tokens=0,
                period_started_at=now,
            )
        )
        # Bring exhausted keys back: allocated if owner exists, else available
        await self.db.execute(
            update(AiProviderKey)
            .where(
                AiProviderKey.status == "exhausted",
                AiProviderKey.allocated_to_license_id.isnot(None),
            )
            .values(status="allocated")
        )
        await self.db.execute(
            update(AiProviderKey)
            .where(
                AiProviderKey.status == "exhausted",
                AiProviderKey.allocated_to_license_id.is_(None),
            )
            .values(status="available")
        )
        await self.db.flush()
        return res.rowcount or 0

    async def mark_health(self, key_id: int, *, success: bool, error: str = "") -> None:
        k = await self.db.get(AiProviderKey, key_id)
        if k is None:
            return
        now = datetime.now(timezone.utc)
        if success:
            k.health_status = "healthy"
            k.consecutive_failures = 0
            k.last_success_at = now
            k.last_error = ""
        else:
            k.consecutive_failures += 1
            k.last_failure_at = now
            k.last_error = (error or "")[:500]
            if k.consecutive_failures >= 5:
                k.health_status = "down"
            elif k.consecutive_failures >= 2:
                k.health_status = "degraded"
        await self.db.flush()

    async def add_tokens_used(self, key_id: int, tokens: int) -> None:
        k = await self.db.get(AiProviderKey, key_id)
        if k is None:
            return
        k.monthly_used_tokens += tokens
        if k.monthly_quota_tokens and k.monthly_used_tokens >= k.monthly_quota_tokens:
            k.status = "exhausted"
        await self.db.flush()
