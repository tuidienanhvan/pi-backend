"""Admin CLI — create a new license and print the key.

Usage:
    python -m scripts.create_license \\
        --plugin pi-seo-pro \\
        --email customer@example.com \\
        --tier pro \\
        --max-sites 3 \\
        --name "Customer Name"
"""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.db import AsyncSessionLocal
from app.shared.license.models import License


async def main(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        lic = License.new(
            plugin=args.plugin,
            email=args.email,
            tier=args.tier,
            max_sites=args.max_sites,
            customer_name=args.name,
        )
        if args.expires_days > 0:
            lic.expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires_days)
        if args.notes:
            lic.notes = args.notes

        db.add(lic)
        await db.commit()
        await db.refresh(lic)

        print("─" * 60)
        print(f"  License created: id={lic.id}")
        print(f"  Key:     {lic.key}")
        print(f"  Plugin:  {lic.plugin}")
        print(f"  Email:   {lic.email}")
        print(f"  Tier:    {lic.tier}")
        print(f"  Sites:   max {lic.max_sites}")
        print(f"  Expires: {lic.expires_at or 'never'}")
        print("─" * 60)
        print("Give this key to the customer → they paste into plugin settings.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create a Pi license")
    p.add_argument("--plugin", required=True, help="e.g. pi-seo-pro, pi-dashboard-pro")
    p.add_argument("--email", required=True)
    p.add_argument("--tier", choices=["free", "pro", "agency"], default="pro")
    p.add_argument("--max-sites", type=int, default=1)
    p.add_argument("--expires-days", type=int, default=365)
    p.add_argument("--name", default="")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    asyncio.run(main(args))
