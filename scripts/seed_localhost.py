import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.saas.models import Tenant, Token
from app.saas.tiers import features_for_tier, monthly_quota_for_tier

async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Create localhost tenant
        q = select(Tenant).where(Tenant.domain == "localhost")
        tenant = (await db.execute(q)).scalar_one_or_none()
        
        if not tenant:
            tenant = Tenant(
                name="Local Development",
                domain="localhost",
                site_url="http://localhost:5173",
                license_key="LOCAL-DEV-TEST",
                tier="max",
                status="active",
                activated_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
                features=features_for_tier("max")
            )
            db.add(tenant)
            await db.flush()
            db.add(
                Token(
                    tenant_id=tenant.id,
                    balance=10000,
                    monthly_quota=monthly_quota_for_tier("max"),
                    used_this_month=0,
                )
            )
            print("Created localhost tenant")
        else:
            print("Localhost tenant already exists")
            
        await db.commit()

if __name__ == "__main__":
    asyncio.run(main())
