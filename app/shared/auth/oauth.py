"""OAuth + Forgot/Reset password endpoints.

Stateless approach:
- Password reset uses short-lived JWT (purpose=password_reset, 15min TTL)
- OAuth state uses short-lived JWT (purpose=oauth_state, 10min TTL)
- No new DB table needed.

Providers supported:
- Google: standard OAuth2 with userinfo endpoint
- GitHub: standard OAuth2 with /user + /user/emails endpoints

Frontend flow:
  1. User clicks "Login with Google" → GET /v1/auth/oauth/google/url
  2. Backend returns { auth_url, state } — frontend redirects browser
  3. Provider redirects to /v1/auth/oauth/google/callback?code=...&state=...
  4. Backend exchanges code for user info, finds/creates User, issues JWT
  5. Backend redirects to frontend_store_url + ?jwt=... (or sets cookie)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DbSession
from app.shared.auth.models import User
from app.shared.auth.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.shared.auth.service import AuthService
from app.shared.email.service import send_email_async
from app.shared.schemas.responses import BaseResponse

router = APIRouter()


# ─── Provider configuration ─────────────────────────────────────────────────


PROVIDERS = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "client_id_key": "oauth_google_client_id",
        "client_secret_key": "oauth_google_client_secret",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "emails_url": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
        "client_id_key": "oauth_github_client_id",
        "client_secret_key": "oauth_github_client_secret",
    },
}


def _get_provider_config(provider: str) -> dict:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise HTTPException(404, f"Unknown OAuth provider: {provider}")
    client_id = getattr(settings, cfg["client_id_key"], "")
    client_secret = getattr(settings, cfg["client_secret_key"], "")
    if not client_id or not client_secret:
        raise HTTPException(
            503,
            f"{provider} OAuth not configured — set {cfg['client_id_key'].upper()} + {cfg['client_secret_key'].upper()} env vars",
        )
    return {**cfg, "client_id": client_id, "client_secret": client_secret}


def _create_state_token(provider: str) -> str:
    """CSRF state — short-lived JWT with nonce."""
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "oauth_state",
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _verify_state_token(state: str, expected_provider: str) -> None:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(400, f"Invalid OAuth state: {e}") from e
    if payload.get("purpose") != "oauth_state":
        raise HTTPException(400, "OAuth state purpose mismatch")
    if payload.get("provider") != expected_provider:
        raise HTTPException(400, "OAuth provider mismatch")


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/oauth/{provider}/url")
async def oauth_authorize_url(
    provider: str,
    redirect_to: str = Query("", description="Frontend URL to redirect after success"),
) -> dict:
    """Return authorization URL + state for the requested provider.

    Frontend usage:
      const { auth_url } = await api.get('/v1/auth/oauth/google/url');
      window.location.href = auth_url;
    """
    cfg = _get_provider_config(provider)
    state = _create_state_token(provider)
    # Encode optional frontend redirect into the state separately if needed;
    # for now, all callbacks redirect to OAUTH_REDIRECT_BASE.
    redirect_uri = f"{settings.oauth_redirect_base}/{provider}"

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "response_type": "code",
    }
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    return {
        "auth_url": f"{cfg['authorize_url']}?{urlencode(params)}",
        "state": state,
        "provider": provider,
    }


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    db: DbSession,
    code: Annotated[str, Query(...)],
    state: Annotated[str, Query(...)],
) -> RedirectResponse:
    """Exchange OAuth code for user info, issue JWT, redirect to frontend.

    On success: 302 to frontend_store_url + #jwt=<token>&user_id=<id>
    On failure: 302 to frontend_store_url + #oauth_error=<reason>
    """
    try:
        _verify_state_token(state, provider)
        cfg = _get_provider_config(provider)
        redirect_uri = f"{settings.oauth_redirect_base}/{provider}"

        # Exchange code for access token
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                cfg["token_url"],
                data={
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code >= 400:
                raise HTTPException(400, f"Token exchange failed: {token_resp.text[:200]}")
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(400, "No access_token in provider response")

            # Fetch user info
            user_resp = await client.get(
                cfg["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if user_resp.status_code >= 400:
                raise HTTPException(400, f"Userinfo failed: {user_resp.text[:200]}")
            ui = user_resp.json()

            # GitHub email may be private — fetch /user/emails separately
            email = ui.get("email")
            if provider == "github" and not email:
                emails_resp = await client.get(
                    cfg["emails_url"],
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if emails_resp.status_code < 400:
                    emails = emails_resp.json()
                    primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                    if primary:
                        email = primary.get("email")

            if not email:
                raise HTTPException(400, f"{provider} did not return a verified email")

            name = ui.get("name") or ui.get("login") or email.split("@")[0]

        # Find or create user
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            user = existing
            user.last_login_at = datetime.now(timezone.utc)
            if not user.is_verified:
                user.is_verified = True  # OAuth implies email is verified
        else:
            # Create new user with random password (they'll never use it — OAuth only)
            from secrets import token_urlsafe
            svc_temp = AuthService(db)
            user = User(
                email=email,
                name=name,
                password_hash=svc_temp.hash_password(token_urlsafe(32)),
                is_verified=True,
            )
            db.add(user)
            await db.flush()

        # Issue JWT
        svc = AuthService(db)
        jwt_token, expires_in = await svc.create_token(user)

        # Redirect to frontend with token in URL fragment (not query — won't be logged)
        redirect = f"{settings.frontend_store_url}/auth/oauth/complete#jwt={jwt_token}&expires_in={expires_in}&user_id={user.id}"
        return RedirectResponse(url=redirect, status_code=302)

    except HTTPException as e:
        # Redirect back to frontend with error
        err_redirect = f"{settings.frontend_store_url}/auth/oauth/complete#oauth_error={e.detail}"
        return RedirectResponse(url=err_redirect, status_code=302)


# ─── Forgot / Reset password ────────────────────────────────────────────────


@router.post("/forgot-password", response_model=BaseResponse[dict])
async def forgot_password(req: ForgotPasswordRequest, db: DbSession) -> BaseResponse[dict]:
    """Send password reset email.

    Always returns success (even if email doesn't exist) to prevent email
    enumeration attack. If email exists, generate JWT reset token and send.
    """
    user = (await db.execute(select(User).where(User.email == req.email.lower()))).scalar_one_or_none()

    # Always return same response shape (no email enumeration)
    if user is not None:
        token = AuthService.create_password_reset_token(user, ttl_minutes=15)
        reset_url = f"{settings.frontend_store_url}/reset-password?token={token}"

        html = f"""
        <!DOCTYPE html>
        <html><body style="font-family:system-ui,-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:24px;">
          <h2 style="color:#111">Đặt lại mật khẩu Pi Ecosystem</h2>
          <p>Xin chào {user.name or user.email},</p>
          <p>Bạn đã yêu cầu đặt lại mật khẩu. Bấm nút dưới đây để tạo mật khẩu mới (link hết hạn sau 15 phút):</p>
          <p style="margin:24px 0;">
            <a href="{reset_url}" style="display:inline-block;background:#000;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;">Đặt lại mật khẩu</a>
          </p>
          <p style="color:#666;font-size:14px;">Hoặc copy link: <br><code style="word-break:break-all;background:#f5f5f5;padding:4px 8px;border-radius:4px;">{reset_url}</code></p>
          <p style="color:#999;font-size:13px;margin-top:32px;border-top:1px solid #eee;padding-top:16px;">
            Nếu bạn không yêu cầu việc này, hãy bỏ qua email. Mật khẩu hiện tại của bạn không thay đổi.
          </p>
        </body></html>
        """
        text = f"Đặt lại mật khẩu Pi Ecosystem\n\nLink: {reset_url}\n\nLink hết hạn sau 15 phút. Bỏ qua email nếu bạn không yêu cầu."
        await send_email_async(
            to=user.email,
            subject="Đặt lại mật khẩu Pi Ecosystem",
            html=html,
            text=text,
        )

    return BaseResponse(
        data={"sent": True},
        message="Nếu email tồn tại trong hệ thống, link đặt lại đã được gửi.",
    )


@router.post("/reset-password", response_model=BaseResponse[dict])
async def reset_password(req: ResetPasswordRequest, db: DbSession) -> BaseResponse[dict]:
    """Verify reset token and set new password."""
    payload = AuthService.verify_password_reset_token(req.token)
    user_id = int(payload["sub"])
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User not found")

    svc = AuthService(db)
    user.password_hash = svc.hash_password(req.new_password)
    await db.flush()

    return BaseResponse(data={"reset": True}, message="Đặt lại mật khẩu thành công.")
