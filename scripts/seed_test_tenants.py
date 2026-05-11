"""Seed development SaaS tenants.

Run from pi-backend:
    python scripts/seed_test_tenants.py
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.saas.models import Tenant, Token
from app.saas.tiers import features_for_tier, monthly_quota_for_tier

DEMO_TENANTS = [
    {
        "id": 2,
        "name": "Demo Pro Customer",
        "domain": "demo-pro.test",
        "license_key": "DEMO-1PRO0-AAAAA-BBBBB",
        "tier": "pro",
        "status": "active",
        "tokens": 1000,
    },
    {
        "id": 3,
        "name": "Demo Free Customer",
        "domain": "demo-free.test",
        "license_key": "DEMO-2FREE-CCCCC-DDDDD",
        "tier": "free",
        "status": "active",
        "tokens": 100,
    },
    {
        "id": 4,
        "name": "Demo Suspended",
        "domain": "demo-susp.test",
        "license_key": "DEMO-3SUSP-EEEEE-FFFFF",
        "tier": "pro",
        "status": "suspended",
        "tokens": 0,
    },
    {
        "id": 5,
        "name": "Local Development",
        "domain": "localhost",
        "license_key": "LOCAL-DEV-TEST",
        "tier": "max",
        "status": "active",
        "tokens": 10000,
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        seeded = 0
        for raw in DEMO_TENANTS:
            data = dict(raw)
            tokens = int(data.pop("tokens"))
            q = select(Tenant).where(Tenant.id == data["id"])
            if (await db.execute(q)).scalar_one_or_none() is not None:
                print(f"Tenant {data['id']} already exists - skip")
                continue

            tenant = Tenant(
                **data,
                site_url=f"https://{data['domain']}",
                features=features_for_tier(str(data["tier"])),
                activated_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
            )
            db.add(tenant)
            await db.flush()
            db.add(
                Token(
                    tenant_id=tenant.id,
                    balance=tokens,
                    monthly_quota=monthly_quota_for_tier(str(data["tier"])),
                    used_this_month=0,
                )
            )
            seeded += 1
        await db.commit()
        print(f"Seeded {seeded} demo tenants")


if __name__ == "__main__":
    asyncio.run(main())
