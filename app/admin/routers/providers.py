"""/v1/admin/providers/* — CRUD + live test for AI providers."""

import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.admin.schemas import (
    AdminProviderCreate,
    AdminProviderItem,
    AdminProviderPatch,
    AdminProvidersResponse,
    AdminProviderTestResult,
)
from app.admin.service import AdminService
from app.core.deps import DbSession
from app.pi_ai_cloud.models import AiProvider
from app.pi_ai_cloud.providers.openai_compat import OpenAICompatAdapter
from app.shared.auth.deps import CurrentAdmin

router = APIRouter()


@router.get("/providers", response_model=AdminProvidersResponse)
async def list_providers(admin: CurrentAdmin, db: DbSession) -> AdminProvidersResponse:  # noqa: ARG001
    items = await AdminService(db).list_providers()
    return AdminProvidersResponse(items=items)


@router.post("/providers", response_model=AdminProviderItem, status_code=201)
async def create_provider(
    payload: AdminProviderCreate, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminProviderItem:
    svc = AdminService(db)
    # Uniqueness check
    existing = (await db.execute(select(AiProvider).where(AiProvider.slug == payload.slug))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"Provider slug '{payload.slug}' already exists")
    p = await svc.create_provider(payload)
    return await svc._provider_to_item(p)


@router.patch("/providers/{provider_id}", response_model=AdminProviderItem)
async def patch_provider(
    provider_id: int,
    payload: AdminProviderPatch,
    admin: CurrentAdmin,  # noqa: ARG001
    db: DbSession,
) -> AdminProviderItem:
    svc = AdminService(db)
    p = await svc.patch_provider(provider_id, payload)
    if p is None:
        raise HTTPException(404, "Provider not found")
    return await svc._provider_to_item(p)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: int, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> None:
    ok = await AdminService(db).delete_provider(provider_id)
    if not ok:
        raise HTTPException(404, "Provider not found")


@router.post("/providers/{provider_id}/test", response_model=AdminProviderTestResult)
async def test_provider(
    provider_id: int, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminProviderTestResult:
    """Send a tiny 'hello' completion to verify key+base_url+model work."""
    p = await db.get(AiProvider, provider_id)
    if p is None:
        raise HTTPException(404, "Provider not found")

    # Only openai_compat supported for now
    if p.adapter != "openai_compat":
        return AdminProviderTestResult(ok=False, latency_ms=0, error=f"Adapter '{p.adapter}' test not implemented")

    # Pick any available key from the pool for this provider
    from app.pi_ai_cloud.models import AiProviderKey

    key_row = (await db.execute(
        select(AiProviderKey)
        .where(AiProviderKey.provider_id == p.id, AiProviderKey.key_value != "")
        .order_by(AiProviderKey.id.asc())
        .limit(1)
    )).scalar_one_or_none()

    api_key = (key_row.key_value if key_row else "").strip()
    if not api_key:
        return AdminProviderTestResult(
            ok=False, latency_ms=0,
            error="No keys in pool for this provider. Add a key via /admin/keys first.",
        )

    adapter = OpenAICompatAdapter()
    started = time.perf_counter()
    try:
        result = await adapter.complete(
            messages=[{"role": "user", "content": "Say 'pong' in one word."}],
            model_id=p.model_id,
            max_tokens=8,
            temperature=0.0,
            api_key=api_key,
            base_url=p.base_url,
        )
        latency = int((time.perf_counter() - started) * 1000)
        return AdminProviderTestResult(ok=True, latency_ms=latency, sample=(result.text or "")[:200])
    except Exception as exc:  # noqa: BLE001
        latency = int((time.perf_counter() - started) * 1000)
        return AdminProviderTestResult(ok=False, latency_ms=latency, error=str(exc)[:500])
