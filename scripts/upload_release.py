"""Admin CLI — register a new plugin release (upload ZIP + add DB row).

Usage:
    python -m scripts.upload_release \\
        --plugin pi-seo \\
        --version 1.3.0 \\
        --zip ./dist/pi-seo-1.3.0.zip \\
        --tier free \\
        --changelog-file ./CHANGELOG-1.3.0.md
"""

import argparse
import asyncio
import hashlib
import shutil
from pathlib import Path

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.shared.updates.models import PluginRelease


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


async def main(args: argparse.Namespace) -> None:
    src = Path(args.zip).resolve()
    if not src.exists():
        raise SystemExit(f"ZIP not found: {src}")

    dest_dir = Path(settings.updates_storage_path) / args.plugin
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{args.plugin}-{args.version}.zip"
    dest = dest_dir / dest_name

    if dest.exists() and not args.force:
        raise SystemExit(f"Release exists (use --force to overwrite): {dest}")

    shutil.copy2(src, dest)
    size = dest.stat().st_size
    digest = _sha256(dest)

    changelog = ""
    if args.changelog_file:
        changelog = Path(args.changelog_file).read_text(encoding="utf-8")
    elif args.changelog:
        changelog = args.changelog

    async with AsyncSessionLocal() as db:
        release = PluginRelease(
            plugin_slug=args.plugin,
            version=args.version,
            tier_required=args.tier,
            zip_path=f"{args.plugin}/{dest_name}",
            zip_size_bytes=size,
            zip_sha256=digest,
            changelog=changelog,
            is_stable=not args.prerelease,
            min_php_version=args.min_php,
            min_wp_version=args.min_wp,
        )
        db.add(release)
        await db.commit()
        await db.refresh(release)

        print("─" * 60)
        print(f"  Release registered: id={release.id}")
        print(f"  Plugin:  {release.plugin_slug}")
        print(f"  Version: {release.version}")
        print(f"  Tier:    {release.tier_required}")
        print(f"  ZIP:     {dest}  ({size:,} bytes)")
        print(f"  SHA256:  {digest}")
        print(f"  Stable:  {release.is_stable}")
        print("─" * 60)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Register a new plugin release")
    p.add_argument("--plugin", required=True, help="e.g. pi-seo, pi-dashboard")
    p.add_argument("--version", required=True, help="semver e.g. 1.3.0")
    p.add_argument("--zip", required=True, help="path to built ZIP")
    p.add_argument("--tier", choices=["free", "pro", "agency"], default="free")
    p.add_argument("--changelog", default="")
    p.add_argument("--changelog-file", default="")
    p.add_argument("--min-php", default="8.3")
    p.add_argument("--min-wp", default="6.0")
    p.add_argument("--prerelease", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    asyncio.run(main(args))
