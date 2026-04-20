"""Seed Pro licenses + allocate keys for quick end-to-end testing.

Creates:
  - 1 License key per plugin slug (7 licenses) at tier=pro
  - Assigns 'pro' package (2M Pi tokens/month) to each
  - Allocates 2 Groq + 2 Gemini + 1 Cerebras keys to each (if pool has them)

Run:
    docker compose exec -T api python -m scripts.seed_pro_licenses
    docker compose exec -T api python -m scripts.seed_pro_licenses --email you@example.com
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.admin.schemas import AdminLicenseCreate
from app.admin.schemas_cloud import AdminAssignPackage
from app.core.db import AsyncSessionLocal
from app.pi_ai_cloud.models import AiPackage, AiProvider, AiProviderKey, LicensePackage
from app.pi_ai_cloud.services.key_allocator import KeyAllocator
from app.shared.license.models import License

PLUGINS = [
    "pi-ai-cloud", "pi-seo", "pi-chatbot", "pi-leads",
    "pi-analytics", "pi-performance", "pi-dashboard",
]

# Auto-allocation: try providers in order, grab whatever's available.
# This spreads the small pool across 7 licenses. With 8 keys in pool and 7
# licenses, each gets ~1 key minimum.
PREFERRED_PROVIDERS = [
    "groq-llama-70b-free", "gemini-2-flash-free", "cerebras-llama-free",
    "mistral-small-free", "cohere-command-free", "openrouter-free",
    "llm7-free", "pollinations-free", "deepseek-chat-trial", "qwen-turbo-trial",
    "siliconflow-qwen-free", "zhipu-glm-flash-free", "moonshot-kimi-free",
]
KEYS_PER_LICENSE_TARGET = 2  # try to allocate this many per customer


async def create_pro_license(db, plugin: str, email: str, name: str) -> License:
    """Idempotent: create if not exists, otherwise return existing."""
    # Check if license already exists for this (email, plugin)
    existing = (await db.execute(
        select(License).where(License.email == email, License.plugin == plugin)
    )).scalar_one_or_none()
    if existing:
        return existing

    lic = License.new(
        plugin=plugin, email=email, tier="pro",
        max_sites=3, customer_name=name,
    )
    lic.expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    db.add(lic)
    await db.flush()
    return lic


async def assign_pro_package(db, license_id: int) -> None:
    existing = await db.get(LicensePackage, license_id)
    now = datetime.now(timezone.utc)
    if existing is None:
        pkg = LicensePackage(
            license_id=license_id, package_slug="pro", status="active",
            activated_at=now, current_period_started_at=now,
        )
        db.add(pkg)
    else:
        existing.package_slug = "pro"
        existing.status = "active"
    await db.flush()


async def allocate_keys_for_license(db, license_id: int) -> dict:
    """Opportunistic allocation: try preferred providers, grab what's free.

    Stops when KEYS_PER_LICENSE_TARGET reached (or pool exhausted).
    """
    alloc = KeyAllocator(db)
    result: dict = {}
    total = 0
    for slug in PREFERRED_PROVIDERS:
        if total >= KEYS_PER_LICENSE_TARGET:
            break
        provider = (await db.execute(
            select(AiProvider).where(AiProvider.slug == slug)
        )).scalar_one_or_none()
        if provider is None:
            continue
        remaining = KEYS_PER_LICENSE_TARGET - total
        picks = await alloc.allocate_to_license(
            license_id=license_id, provider_id=provider.id, count=remaining,
        )
        if picks:
            result[slug] = len(picks)
            total += len(picks)
    return result


async def ensure_pro_package_exists(db) -> None:
    pkg = await db.get(AiPackage, "pro")
    if pkg is None:
        print("⚠️  Pro package not found. Run `python -m scripts.seed_ai_providers` first.")
        sys.exit(1)


async def main(email: str, name: str) -> None:
    async with AsyncSessionLocal() as db:
        await ensure_pro_package_exists(db)

        print(f"\nCustomer: {name} <{email}>")
        print(f"Creating {len(PLUGINS)} Pro licenses…\n")

        for plugin in PLUGINS:
            lic = await create_pro_license(db, plugin, email, name)
            await assign_pro_package(db, lic.id)
            alloc_counts = await allocate_keys_for_license(db, lic.id)

            total_keys = sum(alloc_counts.values())
            print(f"  ✓ {plugin:20} → license #{lic.id:<3}  key={lic.key}")
            print(f"     └─ package=pro, keys allocated: {total_keys}  ({alloc_counts})")

        await db.commit()

        # Summary
        total_licenses = int((await db.execute(
            select(License).where(License.email == email)
        )).all().__len__())
        print(f"\n✓ Done. {email} now owns {total_licenses} Pro licenses.")

        total_keys_alloc = int((await db.execute(
            select(AiProviderKey).where(AiProviderKey.status == "allocated")
        )).all().__len__())
        print(f"  Total allocated keys in pool: {total_keys_alloc}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", default="admin@piwebagency.com", help="Customer email")
    p.add_argument("--name", default="Pi Admin (dev)", help="Customer name")
    args = p.parse_args()
    asyncio.run(main(args.email, args.name))
