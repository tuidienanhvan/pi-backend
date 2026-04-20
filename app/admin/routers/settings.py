"""/v1/admin/settings — global platform config (branding, packs, flags)."""

from fastapi import APIRouter

from app.admin.schemas import (
    AdminSettingsResponse,
    AdminSettingsUpdate,
    BrandingSettings,
    FeatureFlags,
    TokenPack,
)
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


def _to_response(raw: dict) -> AdminSettingsResponse:
    return AdminSettingsResponse(
        branding=BrandingSettings(**raw["branding"]),
        token_packs=[TokenPack(**p) for p in raw["token_packs"]],
        feature_flags=FeatureFlags(**raw["feature_flags"]),
    )


@router.get("/settings", response_model=AdminSettingsResponse)
async def get_settings(admin: CurrentAdmin, db: DbSession) -> AdminSettingsResponse:  # noqa: ARG001
    raw = await AdminService(db).get_settings()
    return _to_response(raw)


@router.put("/settings", response_model=AdminSettingsResponse)
async def update_settings(
    payload: AdminSettingsUpdate, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminSettingsResponse:
    raw = await AdminService(db).update_settings(payload)
    return _to_response(raw)
