import asyncio
import os
from sqlalchemy import select
from app.core.db import get_db
from app.pi_ai_cloud.models import AiPackage

async def update_quotas():
    # We use a session manually since we're running as a script
    from app.core.db import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        # Update Free
        res = await db.execute(select(AiPackage).where(AiPackage.slug == "free"))
        p_free = res.scalar_one_or_none()
        if p_free:
            p_free.token_quota_monthly = 50_000
            print("Updated Free quota to 50,000")

        # Update Pro
        res = await db.execute(select(AiPackage).where(AiPackage.slug == "pro"))
        p_pro = res.scalar_one_or_none()
        if p_pro:
            p_pro.token_quota_monthly = 1_000_000
            print("Updated Pro quota to 1,000,000")

        # Update Max
        res = await db.execute(select(AiPackage).where(AiPackage.slug == "max"))
        p_max = res.scalar_one_or_none()
        if p_max:
            p_max.token_quota_monthly = 3_000_000
            print("Updated Max quota to 3,000,000")
        
        await db.commit()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(update_quotas())
