"""Update server DTOs — plugin update check + download metadata."""

from datetime import datetime

from pydantic import BaseModel


class UpdateCheckResponse(BaseModel):
    success: bool
    current_version: str
    update_available: bool
    latest_version: str
    download_url: str | None = None
    changelog: str = ""
    min_php: str = "8.3"
    min_wp: str = "6.0"
    released_at: datetime | None = None
