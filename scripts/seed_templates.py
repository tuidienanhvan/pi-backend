"""Admin CLI — placeholder seeder.

Schema templates are currently hardcoded in app/prompts/schema_templates.py
and don't need DB seeding. This script exists for future DB-backed templates.

Usage:
    python -m scripts.seed_templates
"""

import asyncio


async def main() -> None:
    print("Templates are currently served from app/prompts/schema_templates.py")
    print("No DB seeding needed.")
    print()
    print("To change templates:")
    print("  1. Edit app/prompts/schema_templates.py")
    print("  2. Restart the API (docker compose restart api)")


if __name__ == "__main__":
    asyncio.run(main())
