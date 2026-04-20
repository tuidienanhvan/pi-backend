"""Telemetry DTOs — plugin heartbeat + anonymous usage stats."""

from pydantic import BaseModel, Field


class TelemetryPingRequest(BaseModel):
    site_url: str
    plugin_slug: str
    plugin_version: str
    wp_version: str = ""
    php_version: str = ""
    active_users: int = 0
    posts_count: int = 0
    extra: dict = Field(default_factory=dict)


class TelemetryPingResponse(BaseModel):
    success: bool = True
    next_ping_hours: int = 24
    admin_notice: str | None = None
