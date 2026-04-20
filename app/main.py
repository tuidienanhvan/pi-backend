"""FastAPI entrypoint — registers all plugin routers.

URL prefix convention:
  /v1/license/*    — shared license (all plugins)
  /v1/updates/*    — shared update server
  /v1/telemetry/*  — shared heartbeat
  /v1/ai/*         — Pi AI Cloud (token-based, primary revenue)
  /v1/seo/*        — Pi SEO Pro
  /v1/chatbot/*    — Pi Chatbot Pro
  /v1/leads/*      — Pi Leads Pro
  /v1/analytics/*  — Pi Analytics Pro
  /v1/perf/*       — Pi Performance Pro
  /v1/dashboard/*  — Pi Dashboard
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app import __version__
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_conf import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware
from app.core.redis_client import close_redis

# Shared
from app.shared.auth.router import router as auth_router
from app.shared.health import router as health_router
from app.shared.license.router import router as license_router
from app.shared.telemetry.router import router as telemetry_router
from app.shared.updates.router import router as updates_router

# Admin domain (requires admin JWT)
from app.admin.routers.overview import router as admin_overview_router
from app.admin.routers.licenses import router as admin_licenses_router
from app.admin.routers.users import router as admin_users_router
from app.admin.routers.providers import router as admin_providers_router
from app.admin.routers.usage import router as admin_usage_router
from app.admin.routers.revenue import router as admin_revenue_router
from app.admin.routers.releases import router as admin_releases_router
from app.admin.routers.settings import router as admin_settings_router
from app.admin.routers.keys import router as admin_keys_router
from app.admin.routers.packages import router as admin_packages_router
from app.admin.routers.audit import router as admin_audit_router
from app.admin.routers.cron import router as admin_cron_router

# Pi AI Cloud (tokens + AI completion)
from app.pi_ai_cloud.routers.complete import router as ai_complete_router
from app.pi_ai_cloud.routers.tokens import router as ai_tokens_router
from app.pi_ai_cloud.routers.cloud import router as ai_cloud_router
from app.pi_ai_cloud.routers.public import router as public_router

# Pi SEO
from app.pi_seo.routers.audit import router as seo_audit_router
from app.pi_seo.routers.schema import router as seo_schema_router
from app.pi_seo.routers.seo_bot import router as seo_bot_router
from app.pi_seo.routers.psi import router as seo_psi_router
from app.pi_seo.routers.indexing import router as seo_indexing_router

# Other plugins (scaffolds)
from app.pi_analytics.routers.events import router as analytics_router
from app.pi_chatbot.routers.chat import router as chatbot_router
from app.pi_dashboard.routers.widgets import router as dashboard_router
from app.pi_leads.routers.leads import router as leads_router
from app.pi_performance.routers.perf import router as perf_router

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info("pi_backend_starting", extra={"version": __version__, "env": settings.app_env})
    yield
    await close_redis()
    logger.info("pi_backend_stopped")


app = FastAPI(
    title="Pi Backend API",
    description=(
        "Backend services for the Pi WordPress ecosystem. "
        "Primary revenue: Pi AI Cloud (token-based). "
        "Plugin-specific endpoints under /v1/{plugin-slug}/*."
    ),
    version=__version__,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# Middleware
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id", "x-response-time-ms"],
)

register_exception_handlers(app)

# Shared
app.include_router(health_router, tags=["health"])
app.include_router(auth_router,      prefix="/v1/auth",      tags=["shared: auth"])
app.include_router(license_router,   prefix="/v1/license",   tags=["shared: license"])
app.include_router(updates_router,   prefix="/v1/updates",   tags=["shared: updates"])
app.include_router(telemetry_router, prefix="/v1/telemetry", tags=["shared: telemetry"])

# Admin (all under /v1/admin, require admin JWT)
app.include_router(admin_overview_router,  prefix="/v1/admin", tags=["admin: overview"])
app.include_router(admin_licenses_router,  prefix="/v1/admin", tags=["admin: licenses"])
app.include_router(admin_users_router,     prefix="/v1/admin", tags=["admin: users"])
app.include_router(admin_providers_router, prefix="/v1/admin", tags=["admin: providers"])
app.include_router(admin_usage_router,     prefix="/v1/admin", tags=["admin: usage"])
app.include_router(admin_revenue_router,   prefix="/v1/admin", tags=["admin: revenue"])
app.include_router(admin_releases_router,  prefix="/v1/admin", tags=["admin: releases"])
app.include_router(admin_settings_router,  prefix="/v1/admin", tags=["admin: settings"])
app.include_router(admin_keys_router,      prefix="/v1/admin", tags=["admin: keys"])
app.include_router(admin_packages_router,  prefix="/v1/admin", tags=["admin: packages"])
app.include_router(admin_audit_router,     prefix="/v1/admin", tags=["admin: audit"])
app.include_router(admin_cron_router,      prefix="/v1/admin", tags=["admin: cron"])

# Pi AI Cloud (primary revenue)
app.include_router(ai_complete_router, prefix="/v1/ai", tags=["pi-ai-cloud: complete"])
app.include_router(ai_tokens_router,   prefix="/v1/ai", tags=["pi-ai-cloud: tokens"])
app.include_router(ai_cloud_router,    prefix="/v1/cloud", tags=["pi-ai-cloud: customer"])
app.include_router(public_router,      prefix="/v1/public", tags=["public"])

# Pi SEO
app.include_router(seo_bot_router,      prefix="/v1/seo/bot",      tags=["pi-seo: ai bot"])
app.include_router(seo_audit_router,    prefix="/v1/seo/audit",    tags=["pi-seo: audit"])
app.include_router(seo_schema_router,   prefix="/v1/seo/schema",   tags=["pi-seo: schema"])
app.include_router(seo_psi_router,      prefix="/v1/seo/psi",      tags=["pi-seo: pagespeed"])
app.include_router(seo_indexing_router, prefix="/v1/seo/indexing", tags=["pi-seo: indexing"])

# Other plugins (scaffolds)
app.include_router(chatbot_router,   prefix="/v1/chatbot",   tags=["pi-chatbot"])
app.include_router(leads_router,     prefix="/v1/leads",     tags=["pi-leads"])
app.include_router(analytics_router, prefix="/v1/analytics", tags=["pi-analytics"])
app.include_router(perf_router,      prefix="/v1/perf",      tags=["pi-performance"])
app.include_router(dashboard_router, prefix="/v1/dashboard", tags=["pi-dashboard"])


@app.get("/", include_in_schema=False)
async def root() -> dict[str, object]:
    return {
        "service": "pi-backend",
        "version": __version__,
        "status": "ok",
        "docs": "/docs" if not settings.is_production else "hidden",
        "plugins": {
            "shared": ["auth", "license", "updates", "telemetry"],
            "admin": ["overview", "licenses", "users", "providers", "usage", "revenue", "releases"],
            "pi-ai-cloud": ["complete", "tokens (primary revenue)"],
            "pi-seo": ["bot", "audit", "schema"],
            "pi-chatbot": ["scaffold"],
            "pi-leads": ["scaffold"],
            "pi-analytics": ["scaffold"],
            "pi-performance": ["scaffold"],
            "pi-dashboard": ["scaffold"],
        },
    }
