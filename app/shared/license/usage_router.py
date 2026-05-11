from fastapi import APIRouter
from app.core.deps import CurrentLicense, DbSession
from app.shared.license.service import LicenseService
from app.shared.license.usage_schemas import UsageReportRequest

router = APIRouter()

@router.post("/report")
async def report_usage(
    req: UsageReportRequest,
    lic: CurrentLicense,
    db: DbSession
) -> dict:
    svc = LicenseService(db)
    await svc.log_usage(
        lic,
        endpoint=f"external.{req.source}",
        site_domain=req.site_url,
        tokens_input=req.tokens_input,
        tokens_output=req.tokens_output
    )
    return {"success": True, "accepted": True}
