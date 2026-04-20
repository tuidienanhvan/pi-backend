"""Stripe billing integration — token top-up.

Call flow:
  1. Customer clicks "Buy 100k tokens" in plugin
  2. Plugin calls POST /v1/ai/topup/checkout → get Stripe Checkout URL
  3. Customer pays on Stripe → webhook hits /v1/ai/stripe/webhook
  4. Webhook credits the wallet
"""

import os

import httpx

from app.core.exceptions import PiException
from app.core.logging_conf import get_logger
from app.pi_ai_cloud.services.wallet import TOPUP_PACKS

logger = get_logger(__name__)


class StripeBilling:
    """Thin Stripe wrapper — no SDK, raw HTTP to avoid dependency bloat."""

    BASE_URL = "https://api.stripe.com/v1"

    def __init__(self) -> None:
        self.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def create_checkout_session(
        self,
        *,
        pack: str,
        license_id: int,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        if not self.enabled:
            raise PiException(503, "billing_disabled", "Stripe not configured")
        if pack not in TOPUP_PACKS:
            raise PiException(400, "invalid_pack", f"Unknown pack: {pack}")

        tokens, price_cents = TOPUP_PACKS[pack]

        payload = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][product_data][name]": f"Pi AI Cloud — {tokens:,} tokens",
            "line_items[0][price_data][unit_amount]": str(price_cents),
            "line_items[0][quantity]": "1",
            "metadata[license_id]": str(license_id),
            "metadata[pack]": pack,
            "metadata[tokens]": str(tokens),
        }

        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                f"{self.BASE_URL}/checkout/sessions",
                data=payload,
                auth=(self.api_key, ""),
            )
        if r.status_code >= 400:
            logger.error("stripe_checkout_error", extra={"body": r.text[:500]})
            raise PiException(502, "stripe_error", f"Stripe HTTP {r.status_code}")

        data = r.json()
        return {
            "session_id": data["id"],
            "checkout_url": data["url"],
        }

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        """Verify Stripe-Signature header + return parsed event.

        Simplified HMAC check — in production use the official `stripe` SDK
        (`stripe.Webhook.construct_event`) which handles timing attacks properly.
        """
        import hashlib
        import hmac
        import json

        if not self.webhook_secret:
            raise PiException(503, "webhook_disabled", "STRIPE_WEBHOOK_SECRET not set")

        # Very simplified — real Stripe signature is "t=...,v1=..." multi-part
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        if expected not in signature:
            raise PiException(401, "invalid_signature", "Webhook signature mismatch")

        return json.loads(payload)
