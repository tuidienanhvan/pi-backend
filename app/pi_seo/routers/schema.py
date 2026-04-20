"""Schema template library endpoints."""

from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentLicense
from app.pi_seo.data.schema_templates import SCHEMA_TEMPLATES, templates_for_tier
from app.pi_seo.schemas import SchemaTemplate, SchemaTemplatesResponse

router = APIRouter()


@router.get("/templates", response_model=SchemaTemplatesResponse)
async def list_templates(lic: CurrentLicense) -> SchemaTemplatesResponse:
    """Return all templates visible to this license tier."""
    templates = templates_for_tier(lic.tier)
    return SchemaTemplatesResponse(
        success=True,
        templates=templates,
        total=len(templates),
    )


@router.get("/templates/{template_id}", response_model=SchemaTemplate)
async def get_template(template_id: str, lic: CurrentLicense) -> SchemaTemplate:
    """Return a single template — 404 if not visible to tier."""
    allowed = {t.id for t in templates_for_tier(lic.tier)}
    if template_id not in allowed:
        raise HTTPException(404, "Template not found or not in your tier")

    for t in SCHEMA_TEMPLATES:
        if t.id == template_id:
            return t
    raise HTTPException(404, "Template not found")
