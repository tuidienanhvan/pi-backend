"""Pi Dashboard — widgets + cross-plugin metadata (SCAFFOLD).

Most of Pi Dashboard's work is client-side. This backend surface is small:
  GET  /v1/dashboard/overview    — aggregated stats (used by dashboard widget)
  POST /v1/dashboard/audit-log   — record admin actions (Pro tier)
"""

from fastapi import APIRouter

from app.core.deps import CurrentLicense

router = APIRouter()


@router.get("/status")
async def status(lic: CurrentLicense) -> dict:
    return {
        "plugin": "pi-dashboard",
        "tier": lic.tier,
        "phase": "scaffold — endpoints coming soon",
    }
