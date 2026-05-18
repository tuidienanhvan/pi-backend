"""/v1/admin/releases — list + upload plugin releases."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from app.admin.schemas import AdminReleaseItem, AdminReleasesResponse
from app.core.config import settings
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin
from app.shared.updates.models import PluginRelease

router = APIRouter()


@router.get("/releases", response_model=AdminReleasesResponse)
async def list_releases(admin: CurrentAdmin, db: DbSession) -> AdminReleasesResponse:  # noqa: ARG001
    q = select(PluginRelease).order_by(PluginRelease.created_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return AdminReleasesResponse(items=[
        AdminReleaseItem(
            id=r.id, plugin_slug=r.plugin_slug, version=r.version,
            tier_required=r.tier_required, zip_size_bytes=r.zip_size_bytes,
            zip_sha256=r.zip_sha256, is_stable=r.is_stable, is_yanked=r.is_yanked,
            created_at=r.created_at,
        ) for r in rows
    ])


@router.post("/releases")
async def upload_release(
    admin: CurrentAdmin,
    db: DbSession,
    plugin_slug: str = Form(...),
    version: str = Form(...),
    tier_required: str = Form("free"),
    changelog: str = Form(""),
    min_php: str = Form("8.3"),
    min_wp: str = Form("6.0"),
    is_stable: bool = Form(True),
    zip: UploadFile = File(...),
) -> dict:
    """Save uploaded ZIP + create DB row."""
    if zip.content_type not in ("application/zip", "application/x-zip-compressed"):
        raise HTTPException(400, f"Expected ZIP, got {zip.content_type}")

    storage_root = Path(settings.updates_storage_path) / plugin_slug
    storage_root.mkdir(parents=True, exist_ok=True)
    dest = storage_root / f"{plugin_slug}-{version}.zip"

    content = await zip.read()
    dest.write_bytes(content)
    size = dest.stat().st_size
    digest = hashlib.sha256(content).hexdigest()

    # Check duplicate
    existing = (await db.execute(
        select(PluginRelease).where(
            PluginRelease.plugin_slug == plugin_slug,
            PluginRelease.version == version,
        )
    )).scalar_one_or_none()
    if existing:
        # Update existing (overwrite behavior)
        existing.zip_path = f"{plugin_slug}/{plugin_slug}-{version}.zip"
        existing.zip_size_bytes = size
        existing.zip_sha256 = digest
        existing.tier_required = tier_required
        existing.changelog = changelog
        existing.is_stable = is_stable
        existing.min_php_version = min_php
        existing.min_wp_version = min_wp
        await db.flush()
        return {"success": True, "id": existing.id, "overwrote": True}

    release = PluginRelease(
        plugin_slug=plugin_slug,
        version=version,
        tier_required=tier_required,
        zip_path=f"{plugin_slug}/{plugin_slug}-{version}.zip",
        zip_size_bytes=size,
        zip_sha256=digest,
        changelog=changelog,
        is_stable=is_stable,
        min_php_version=min_php,
        min_wp_version=min_wp,
    )
    db.add(release)
    await db.flush()
    return {"success": True, "id": release.id}


# ─── Release lifecycle (T-20260518-022) ───────────────────────

@router.patch("/releases/{release_id}")
async def update_release(
    release_id: int,
    payload: dict,
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
) -> dict:
    """Toggle is_stable / is_yanked + edit changelog (T-20260518-022).

    Promote stable: PATCH { is_stable: true } — clears any other stable for
    same plugin_slug. Yank: PATCH { is_yanked: true } — release no longer
    served to /v1/updates/check (rollback).
    """
    release = await db.get(PluginRelease, release_id)
    if release is None:
        raise HTTPException(404, "Release not found")

    if "is_stable" in payload:
        new_stable = bool(payload["is_stable"])
        if new_stable:
            # Demote any other stable releases for same plugin_slug
            others = (await db.execute(
                select(PluginRelease).where(
                    PluginRelease.plugin_slug == release.plugin_slug,
                    PluginRelease.id != release_id,
                    PluginRelease.is_stable.is_(True),
                )
            )).scalars().all()
            for o in others:
                o.is_stable = False
        release.is_stable = new_stable

    if "is_yanked" in payload:
        release.is_yanked = bool(payload["is_yanked"])

    if "changelog" in payload:
        release.changelog = str(payload["changelog"])[:5000]

    if "tier_required" in payload and payload["tier_required"] in ("free", "pro", "max", "enterprise"):
        release.tier_required = payload["tier_required"]

    await db.commit()
    await db.refresh(release)

    return {
        "success": True,
        "id": release.id,
        "is_stable": release.is_stable,
        "is_yanked": release.is_yanked,
    }


@router.delete("/releases/{release_id}", status_code=204)
async def delete_release(
    release_id: int,
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
) -> None:
    """Hard-delete a release (T-20260518-022).

    Removes DB row. Storage cleanup is best-effort. Use yank for soft removal.
    """
    release = await db.get(PluginRelease, release_id)
    if release is None:
        raise HTTPException(404, "Release not found")

    # Best-effort: remove file from storage
    try:
        path = Path(settings.updates_storage_path) / release.zip_path
        if path.exists():
            path.unlink()
    except Exception:  # noqa: BLE001
        pass

    await db.delete(release)
    await db.commit()
