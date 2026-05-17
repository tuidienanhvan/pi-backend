"""One-off: promote an existing admin's license tier to enterprise.

Usage:
    railway run .venv/Scripts/python.exe -X utf8 -m scripts.promote_admin_to_enterprise --email <admin-email>

Idempotent — running twice has no extra effect.
"""

import argparse
import asyncio

from sqlalchemy import select, update

from app.core.db import AsyncSessionLocal
from app.shared.license.models import License


async def main(email: str) -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(License).where(License.email == email))
        ).scalars().all()

        if not rows:
            print(f"No license found for {email}")
            return

        for lic in rows:
            old_tier = lic.tier
            old_sites = lic.max_sites
            lic.tier = "enterprise"
            lic.max_sites = -1  # unlimited
            print(
                f"  license #{lic.id:<3} plugin={lic.plugin:20} "
                f"tier {old_tier} -> enterprise, max_sites {old_sites} -> unlimited"
            )

        await db.commit()
        print(f"\nDone. {len(rows)} license(s) promoted to enterprise for {email}.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    args = p.parse_args()
    asyncio.run(main(args.email))
