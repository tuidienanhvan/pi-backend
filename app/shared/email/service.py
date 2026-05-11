"""Small SMTP email helper used by billing webhooks.

If SMTP is not configured, email delivery is skipped and logged. This keeps
local Stripe webhook tests deterministic while leaving production integration
ready through environment variables.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from string import Template

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
