"""Seed DUMMY keys into the pool for local dev testing.

These are placeholder strings (not real API keys). Real backend calls will
fail — but license allocation + quota tracking flow can be tested.

Run:
    docker compose exec -T api python -m scripts.seed_pool_keys

Replace keys via /admin/keys UI when you get real ones.
"""

import asyncio

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.pi_ai_cloud.models import AiProvider, AiProviderKey

# Provider slug -> (count, dummy-prefix)
POOL_SEED = [
    ("groq-llama-70b-free",    10, "gsk_"),
    ("gemini-2-flash-free",    10, "AIzaSy"),
    ("cerebras-llama-free",    6,  "csk_"),
    ("mistral-small-free",     4,  "mist_"),
    ("cohere-command-free",    4,  "co_"),
    ("openrouter-free",        4,  "sk-or-"),
    ("siliconflow-qwen-free",  3,  "sf_"),
    ("github-models-free",     3,  "ghp_"),
    ("cloudflare-llama-free",  3,  "cf_"),
    ("nvidia-nim-free",        3,  "nvapi-"),
    ("zhipu-glm-flash-free",   2,  "zp_"),
    ("moonshot-kimi-free",     2,  "sk-ms-"),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Load providers
        providers = {
            p.slug: p for p in (await db.execute(select(AiProvider))).scalars().all()
        }

        added = 0
        skipped = 0
        for slug, count, prefix in POOL_SEED:
            provider = providers.get(slug)
            if provider is None:
                print(f"  ⚠️  Provider '{slug}' not found — skipping")
                continue

            # Check existing dummy keys (idempotent)
            existing_q = select(AiProviderKey).where(
                AiProviderKey.provider_id == provider.id,
                AiProviderKey.label.like(f"dummy-{slug}%"),
            )
            existing = (await db.execute(existing_q)).scalars().all()
            existing_count = len(existing)

            need = count - existing_count
            if need <= 0:
                print(f"  ↻ {slug:30} already has {existing_count} keys")
                skipped += existing_count
                continue

            for i in range(existing_count, count):
                k = AiProviderKey(
                    provider_id=provider.id,
                    key_value=f"{prefix}DUMMY_{slug}_{i:03d}_REPLACE_ME",
                    label=f"dummy-{slug}-{i:02d}",
                    status="available",
                    notes="Placeholder for dev testing. Replace with real key via /admin/keys.",
                )
                db.add(k)
                added += 1

            print(f"  + {slug:30} added {need} dummy keys ({existing_count + need} total)")

        await db.commit()
        print(f"\n✓ Done. Added {added} new keys. {skipped} already existed.")


if __name__ == "__main__":
    asyncio.run(main())
