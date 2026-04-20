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
