"""Plugin update server — check + download ZIPs."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentLicense, DbSession
from app.shared.updates.models import PluginRelease
from app.shared.updates.schemas import UpdateCheckResponse

router = APIRouter()


@router.get("/check/{plugin_slug}", response_model=UpdateCheckResponse)
async def check_update(
    plugin_slug: str,
    current: str,
    lic: CurrentLicense,
    db: DbSession,
) -> UpdateCheckResponse:
    """Check if a newer version exists for this plugin + license tier.

    Query args:
        current=1.3.0   (the version installed on the client)
    """
    # Find latest stable release visible to this tier
    q = (
        select(PluginRelease)
        .where(
            PluginRelease.plugin_slug == plugin_slug,
            PluginRelease.is_stable.is_(True),
            PluginRelease.is_yanked.is_(False),
            PluginRelease.tier_required.in_(_tiers_visible(lic.tier)),
        )
        .order_by(PluginRelease.created_at.desc())
        .limit(1)
    )
    result = await db.execute(q)
    release = result.scalar_one_or_none()

    if release is None:
        return UpdateCheckResponse(
            success=True,
            current_version=current,
            update_available=False,
            latest_version=current,
        )

    update_available = _version_compare(release.version, current) > 0
    download_url = None
    if update_available:
        download_url = (
            f"{settings.app_base_url}/v1/updates/download/{plugin_slug}/{release.version}"
        )

    return UpdateCheckResponse(
        success=True,
        current_version=current,
        update_available=update_available,
        latest_version=release.version,
        download_url=download_url,
        changelog=release.changelog,
        min_php=release.min_php_version,
        min_wp=release.min_wp_version,
        released_at=release.created_at,
    )


@router.get("/download/{plugin_slug}/{version}")
async def download(
    plugin_slug: str,
    version: str,
    lic: CurrentLicense,
    db: DbSession,
) -> FileResponse:
    """Stream the ZIP — gated by license tier."""
    q = select(PluginRelease).where(
        PluginRelease.plugin_slug == plugin_slug,
        PluginRelease.version == version,
        PluginRelease.is_yanked.is_(False),
    )
    result = await db.execute(q)
    release = result.scalar_one_or_none()
    if release is None:
        raise HTTPException(404, "Release not found")

    if release.tier_required not in _tiers_visible(lic.tier):
        raise HTTPException(
            403, f"Release requires {release.tier_required} tier, license is {lic.tier}"
        )

    path = Path(settings.updates_storage_path) / release.zip_path
    if not path.exists():
        raise HTTPException(500, "Release file missing on server")

    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{plugin_slug}-{version}.zip",
    )


# ─── Helpers ────────────────────────────────────────────────
def _tiers_visible(tier: str) -> list[str]:
    """Higher tiers can download lower-tier releases."""
    if tier == "agency":
        return ["free", "pro", "agency"]
    if tier == "pro":
        return ["free", "pro"]
    return ["free"]


def _version_compare(a: str, b: str) -> int:
    """Semver-like compare. Return 1 if a>b, 0 if eq, -1 if a<b."""
    pa = [int(x) for x in a.split(".") if x.isdigit()]
    pb = [int(x) for x in b.split(".") if x.isdigit()]
    for x, y in zip(pa, pb, strict=False):
        if x > y:
            return 1
        if x < y:
            return -1
    if len(pa) > len(pb):
        return 1
    if len(pa) < len(pb):
        return -1
    return 0


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
