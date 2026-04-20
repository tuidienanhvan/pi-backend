"""/v1/admin/keys/* — pool management for upstream AI provider keys."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.admin.audit import AuditLogger
from app.admin.schemas_cloud import (
    AdminKeyAllocate,
    AdminKeyBulkImport,
    AdminKeyBulkResult,
    AdminKeyCreate,
    AdminKeyItem,
    AdminKeyPatch,
    AdminKeysResponse,
    AdminPoolSummary,
    AdminPoolSummaryRow,
)
from app.core.deps import DbSession
from app.pi_ai_cloud.models import AiProvider, AiProviderKey
from app.pi_ai_cloud.services.key_allocator import KeyAllocator
from app.shared.auth.deps import CurrentAdmin
from app.shared.license.models import License

router = APIRouter()


def _req_ctx(req: Request) -> dict:
    return {
        "ip_address": req.client.host if req.client else "",
        "user_agent": req.headers.get("user-agent", "")[:500],
        "request_id": req.headers.get("x-request-id", ""),
    }


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


async def _to_item(db, k: AiProviderKey) -> AdminKeyItem:
    provider = await db.get(AiProvider, k.provider_id)
    owner_email = None
    if k.allocated_to_license_id:
        lic = await db.get(License, k.allocated_to_license_id)
        owner_email = lic.email if lic else None
    return AdminKeyItem(
        id=k.id,
        provider_id=k.provider_id,
        provider_slug=provider.slug if provider else "",
        provider_display_name=provider.display_name if provider else "",
        label=k.label,
        key_masked=_mask(k.key_value),
        status=k.status,
        allocated_to_license_id=k.allocated_to_license_id,
        allocated_to_email=owner_email,
        allocated_at=k.allocated_at,
        health_status=k.health_status,
        consecutive_failures=k.consecutive_failures,
        last_error=k.last_error or "",
        last_success_at=k.last_success_at,
        monthly_used_tokens=k.monthly_used_tokens,
        monthly_quota_tokens=k.monthly_quota_tokens,
        notes=k.notes or "",
    )


@router.get("/keys/summary", response_model=AdminPoolSummary)
async def pool_summary(admin: CurrentAdmin, db: DbSession) -> AdminPoolSummary:  # noqa: ARG001
    rows = await KeyAllocator(db).pool_summary()
    return AdminPoolSummary(items=[AdminPoolSummaryRow(**r) for r in rows])


@router.get("/keys", response_model=AdminKeysResponse)
async def list_keys(
    admin: CurrentAdmin, db: DbSession,  # noqa: ARG001
    provider_id: int | None = Query(None),
    status: str | None = Query(None),
    health_status: str | None = Query(None),
    has_errors: bool | None = Query(None),
    license_id: int | None = Query(None),
    q: str = Query(""),
    sort: str = Query("-id"),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
) -> AdminKeysResponse:
    items, total = await KeyAllocator(db).list_keys(
        provider_id=provider_id, status=status,
        health_status=health_status, has_errors=has_errors,
        license_id=license_id, q=q, sort=sort,
        limit=limit, offset=offset,
    )
    return AdminKeysResponse(
        items=[await _to_item(db, k) for k in items],
        total=total,
    )


@router.post("/keys", response_model=AdminKeyItem, status_code=201)
async def create_key(
    payload: AdminKeyCreate, admin: CurrentAdmin, db: DbSession, request: Request,
) -> AdminKeyItem:
    provider_id = payload.provider_id
    if provider_id is None and payload.provider_slug:
        q = select(AiProvider).where(AiProvider.slug == payload.provider_slug)
        p = (await db.execute(q)).scalar_one_or_none()
        if p is None:
            raise HTTPException(404, f"Provider '{payload.provider_slug}' not found")
        provider_id = p.id
    if provider_id is None:
        raise HTTPException(422, "provider_id or provider_slug required")

    k = await KeyAllocator(db).add_key(
        provider_id=provider_id, key_value=payload.key_value, label=payload.label,
        monthly_quota_tokens=payload.monthly_quota_tokens, notes=payload.notes,
    )
    provider = await db.get(AiProvider, provider_id)
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="create", resource_type="key", resource_id=k.id,
        resource_label=f"{provider.slug if provider else '?'} / {payload.label or '(no label)'}",
        after={"provider_slug": provider.slug if provider else "", "label": k.label},
        message=f"Added key #{k.id} to {provider.slug if provider else 'unknown'} pool",
        **_req_ctx(request),
    )
    return await _to_item(db, k)


@router.post("/keys/bulk", response_model=AdminKeyBulkResult)
async def bulk_import_keys(
    payload: AdminKeyBulkImport, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminKeyBulkResult:
    res = await KeyAllocator(db).bulk_import([r.model_dump() for r in payload.rows])
    return AdminKeyBulkResult(**res)


@router.patch("/keys/{key_id}", response_model=AdminKeyItem)
async def patch_key(
    key_id: int, payload: AdminKeyPatch, admin: CurrentAdmin, db: DbSession  # noqa: ARG001
) -> AdminKeyItem:
    k = await db.get(AiProviderKey, key_id)
    if k is None:
        raise HTTPException(404, "Key not found")
    for field in ("key_value", "label", "status", "monthly_quota_tokens", "notes"):
        val = getattr(payload, field, None)
        if val is not None:
            setattr(k, field, val)
    await db.flush()
    return await _to_item(db, k)


@router.delete("/keys/{key_id}", status_code=204)
async def delete_key(
    key_id: int, admin: CurrentAdmin, db: DbSession, request: Request,
) -> None:
    k = await db.get(AiProviderKey, key_id)
    if k is None:
        raise HTTPException(404, "Key not found")
    provider = await db.get(AiProvider, k.provider_id)
    before_label = f"{provider.slug if provider else '?'} / {k.label}"
    ok = await KeyAllocator(db).delete_key(key_id)
    if not ok:
        raise HTTPException(404, "Key not found")
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="delete", resource_type="key", resource_id=key_id,
        resource_label=before_label,
        message=f"Deleted key #{key_id} ({before_label})",
        severity="warning", **_req_ctx(request),
    )


@router.post("/keys/allocate", response_model=list[AdminKeyItem])
async def allocate_keys(
    payload: AdminKeyAllocate, admin: CurrentAdmin, db: DbSession, request: Request,
) -> list[AdminKeyItem]:
    """Either allocate N keys from pool (by provider) OR assign specific key_ids."""
    alloc = KeyAllocator(db)
    lic = await db.get(License, payload.license_id)
    if lic is None:
        raise HTTPException(404, f"License {payload.license_id} not found")

    assigned: list[AiProviderKey] = []
    if payload.key_ids:
        for kid in payload.key_ids:
            k = await alloc.allocate_specific(kid, payload.license_id)
            if k is None:
                raise HTTPException(404, f"Key {kid} not found or not assignable")
            assigned.append(k)
    elif payload.provider_id:
        picks = await alloc.allocate_to_license(
            license_id=payload.license_id,
            provider_id=payload.provider_id,
            count=payload.count,
        )
        if len(picks) < payload.count:
            raise HTTPException(
                409,
                f"Only {len(picks)} available keys in pool for provider {payload.provider_id} (wanted {payload.count})",
            )
        assigned.extend(picks)
    else:
        raise HTTPException(422, "provider_id or key_ids required")

    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="allocate", resource_type="key", resource_id=payload.license_id,
        resource_label=f"license #{payload.license_id}",
        after={"allocated_key_ids": [k.id for k in assigned]},
        message=f"Allocated {len(assigned)} keys to license #{payload.license_id}",
        **_req_ctx(request),
    )
    return [await _to_item(db, k) for k in assigned]


@router.get("/keys/{key_id}/reveal")
async def reveal_key(
    key_id: int, admin: CurrentAdmin, db: DbSession, request: Request,
) -> dict:
    """Return the full key_value for admin. Audited — never anonymous."""
    k = await db.get(AiProviderKey, key_id)
    if k is None:
        raise HTTPException(404, "Key not found")
    provider = await db.get(AiProvider, k.provider_id)
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="update", resource_type="key", resource_id=key_id,
        resource_label=f"{provider.slug if provider else '?'} / {k.label}",
        message=f"Admin revealed raw key #{key_id}",
        severity="warning", **_req_ctx(request),
    )
    return {
        "id": k.id,
        "provider_slug": provider.slug if provider else "",
        "label": k.label,
        "key_value": k.key_value,
    }


@router.post("/keys/{key_id}/revoke", response_model=AdminKeyItem)
async def revoke_key(
    key_id: int, admin: CurrentAdmin, db: DbSession, request: Request,
) -> AdminKeyItem:
    k = await KeyAllocator(db).revoke_key(key_id)
    if k is None:
        raise HTTPException(404, "Key not found")
    await AuditLogger.log(
        db, actor_id=admin.id, actor_email=admin.email,
        action="revoke", resource_type="key", resource_id=key_id,
        resource_label=f"key #{key_id}",
        message=f"Revoked key #{key_id} — returned to available pool",
        **_req_ctx(request),
    )
    return await _to_item(db, k)


@router.post("/keys/reset-period", status_code=200)
async def reset_period(admin: CurrentAdmin, db: DbSession) -> dict:  # noqa: ARG001
    """Manually trigger monthly reset (cron calls this)."""
    n = await KeyAllocator(db).reset_monthly_counters()
    return {"reset_count": n}
