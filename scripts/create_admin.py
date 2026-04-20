"""Admin CLI — create the first admin user for the dashboard.

Usage:
    python -m scripts.create_admin \\
        --email admin@piwebagency.com \\
        --password "SuperSecret!" \\
        --name "Pi Admin"
"""

import argparse
import asyncio
import getpass

from app.core.db import AsyncSessionLocal
from app.shared.auth.service import AuthService


async def main(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        raise SystemExit("Password must be >= 8 chars")

    async with AsyncSessionLocal() as db:
        svc = AuthService(db)
        existing = await svc.get_by_email(args.email)
        if existing:
            if args.force:
                existing.is_admin = True
                existing.is_verified = True
                existing.password_hash = AuthService.hash_password(password)
                await db.commit()
                print(f"✓ Updated existing user {args.email} → is_admin=True")
            else:
                raise SystemExit(f"User {args.email} already exists. Use --force to promote/reset.")
            return

        user = await svc.create_user(
            email=args.email,
            password=password,
            name=args.name,
            is_admin=True,
        )
        user.is_verified = True
        await db.commit()
        await db.refresh(user)

        print("─" * 60)
        print(f"  Admin user created: id={user.id}")
        print(f"  Email: {user.email}")
        print(f"  Name:  {user.name}")
        print(f"  Role:  {'ADMIN' if user.is_admin else 'user'}")
        print("─" * 60)
        print("  Use this to sign in at store.pi-ecosystem.com/login")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create a Pi admin user")
    p.add_argument("--email", required=True)
    p.add_argument("--password", default="", help="Leave empty to prompt interactively")
    p.add_argument("--name", default="Admin")
    p.add_argument("--force", action="store_true", help="Promote + reset password if user exists")
    args = p.parse_args()

    asyncio.run(main(args))
