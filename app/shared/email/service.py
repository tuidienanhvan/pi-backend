"""Email helper — Resend API (primary) + SMTP (fallback) + dev no-op.

Provider selection order:
  1. Resend API if `resend_api_key` set (free tier 3k emails/month)
  2. SMTP if `smtp_host` set (Gmail, Brevo, Mailtrap, etc.)
  3. No-op + log warning (dev mode)
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging_conf import get_logger

logger = get_logger(__name__)


def _template_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "emails" / f"{name}.html"


def render_template(name: str, context: dict[str, object]) -> str:
    path = _template_path(name)
    html = path.read_text(encoding="utf-8")
    return Template(html).safe_substitute({k: str(v) for k, v in context.items()})


def send_email(*, to: str, subject: str, template: str, context: dict[str, object]) -> bool:
    if not to:
        logger.info("email_skip_missing_recipient", extra={"template": template})
        return False

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("SMTP_FROM_EMAIL", "no-reply@pi-ecosystem.com")

    html = render_template(template, context)
    if not host:
        logger.info("email_skip_smtp_not_configured", extra={"to": to, "subject": subject, "template": template})
        return False

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("Open this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)
    return True


# ─── Async API (preferred for FastAPI endpoints) ─────────────────────────────


async def send_email_async(
    *,
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
) -> bool:
    """Async email send with Resend primary + SMTP fallback + dev no-op.

    Returns True if sent, False if dev mode (no provider configured) — never
    raises on send failure (logs warning instead) so password reset flow
    doesn't expose whether email exists in DB.
    """
    if not to:
        logger.warning("email_skip_missing_recipient", extra={"subject": subject})
        return False

    text_fallback = text or "Open this email in an HTML-capable client."

    # ── Provider 1: Resend API ────────────────────────────────
    if settings.resend_api_key:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": settings.email_from,
                        "to": [to],
                        "subject": subject,
                        "html": html,
                        "text": text_fallback,
                        **({"reply_to": settings.email_reply_to} if settings.email_reply_to else {}),
                    },
                )
            if resp.status_code >= 400:
                logger.warning(
                    "email_resend_failed",
                    extra={"to": to, "status": resp.status_code, "body": resp.text[:300]},
                )
                return False
            logger.info("email_sent_resend", extra={"to": to, "subject": subject})
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("email_resend_error", extra={"to": to, "err": str(exc)[:200]})
            # Fall through to SMTP

    # ── Provider 2: SMTP ──────────────────────────────────────
    if settings.smtp_host:
        try:
            msg = EmailMessage()
            msg["From"] = settings.email_from
            msg["To"] = to
            msg["Subject"] = subject
            if settings.email_reply_to:
                msg["Reply-To"] = settings.email_reply_to
            msg.set_content(text_fallback)
            msg.add_alternative(html, subtype="html")

            # smtplib is sync; run in threadpool to avoid blocking event loop
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _send_smtp_blocking, msg)
            logger.info("email_sent_smtp", extra={"to": to, "subject": subject})
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("email_smtp_error", extra={"to": to, "err": str(exc)[:200]})
            return False

    # ── Provider 3: Dev no-op ─────────────────────────────────
    logger.warning(
        "email_dev_no_op",
        extra={"to": to, "subject": subject, "hint": "Set RESEND_API_KEY or SMTP_HOST"},
    )
    if settings.app_env == "development":
        # Print to stdout in dev so devs can copy-paste links
        print(f"\n=== EMAIL (dev no-op) ===\nTo: {to}\nSubject: {subject}\n\n{html}\n=========================\n")
    return False


def _send_smtp_blocking(msg: EmailMessage) -> None:
    """Blocking SMTP send — called via run_in_executor."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
