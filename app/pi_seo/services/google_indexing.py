"""Real Google Indexing API submission via service account JWT.

Requires:
  - pip install google-auth
  - GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON env var set to:
    a) path to the service-account JSON file, OR
    b) the inline JSON string itself (for Railway/container envs)

Docs: https://developers.google.com/search/apis/indexing-api/v3/quickstart
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging_conf import get_logger

logger = get_logger(__name__)

INDEXING_API_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]

_cached_creds: Any = None


def _get_credentials() -> Any:
    """Load service account credentials from file path or inline JSON.

    Returns google.oauth2.service_account.Credentials or None if not configured
    or google-auth is not installed.
    """
    global _cached_creds
    if _cached_creds is not None:
        return _cached_creds

    raw = settings.google_indexing_service_account_json
    if not raw:
        return None

    try:
        from google.oauth2 import service_account
    except ImportError:
        logger.warning("google-auth not installed — Google Indexing API unavailable")
        return None

    # Support both file path and inline JSON
    if raw.strip().startswith("{"):
        info = json.loads(raw)
    else:
        path = Path(raw)
        if not path.exists():
            logger.error("Service account JSON file not found: %s", raw)
            return None
        info = json.loads(path.read_text(encoding="utf-8"))

    _cached_creds = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES,
    )
    return _cached_creds


async def submit_to_google(url: str, action: str = "URL_UPDATED") -> dict:
    """Submit URL to Google Indexing API.

    Returns:
        {"submitted": True, "response": {...}} on success
        {"submitted": False, "error": "..."} on failure
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "submitted": False,
            "error": "google_indexing_service_account_json not configured or google-auth not installed",
        }

    # Refresh token if needed (sync call — wrap in executor for async safety)
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest

        loop = asyncio.get_event_loop()
        if not creds.valid:
            await loop.run_in_executor(None, lambda: creds.refresh(GoogleAuthRequest()))
    except Exception as e:
        logger.error("Failed to refresh Google auth token: %s", e)
        return {"submitted": False, "error": f"Token refresh failed: {e}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                INDEXING_API_URL,
                headers={
                    "Authorization": f"Bearer {creds.token}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "type": action},
            )

        if resp.status_code >= 400:
            error_text = resp.text[:300]
            logger.warning(
                "Google Indexing API error %d for %s: %s",
                resp.status_code, url, error_text,
            )
            return {
                "submitted": False,
                "error": f"Google API {resp.status_code}: {error_text}",
            }

        logger.info("Google Indexing API success for %s (action=%s)", url, action)
        return {"submitted": True, "response": resp.json()}

    except httpx.TimeoutException:
        return {"submitted": False, "error": "Google API request timed out (30s)"}
    except Exception as e:
        logger.error("Google Indexing API exception for %s: %s", url, e)
        return {"submitted": False, "error": str(e)}
