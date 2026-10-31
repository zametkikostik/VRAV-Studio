from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class Money(BaseModel):
    amount: Decimal
    currency: str = "USD"


class CheckoutRequest(BaseModel):
    organization_id: str
    plan_id: str | None = None
    amount: Money
    success_url: str
    cancel_url: str
    metadata: dict[str, Any] | None = None


class CheckoutSession(BaseModel):
    id: str
    url: str
    provider: str = "stripe"


class WebhookResult(BaseModel):
    event_type: str
    payment_id: str | None = None
    status: str
    raw: dict[str, Any]


class StripePaymentProvider:
    id = "stripe"

    def __init__(self, secret_key: str | None = None, webhook_secret: str | None = None):
        self.secret_key = secret_key if secret_key is not None else os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = webhook_secret if webhook_secret is not None else os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.use_sdk = os.getenv("STRIPE_USE_SDK", "").lower() in ("1", "true", "yes")
        self.allow_live = os.getenv("STRIPE_ALLOW_LIVE", "").lower() in ("1", "true", "yes")

    def _assert_key_policy(self) -> None:
        if self.secret_key.startswith("sk_live") and not self.allow_live:
            raise RuntimeError(
                "Live Stripe keys blocked. Set STRIPE_ALLOW_LIVE=1 only on hardened production."
            )

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutSession:
        self._assert_key_policy()
        if self.use_sdk and self.secret_key:
            try:
                import stripe

                stripe.api_key = self.secret_key
                session = stripe.checkout.Session.create(
                    mode="payment",
                    success_url=req.success_url,
                    cancel_url=req.cancel_url,
                    line_items=[{
                        "price_data": {
                            "currency": req.amount.currency.lower(),
                            "product_data": {"name": req.plan_id or "VRAV credits"},
                            "unit_amount": int(req.amount.amount * 100),
                        },
                        "quantity": 1,
                    }],
                    metadata={"organization_id": req.organization_id, **(req.metadata or {})},
                )
                return CheckoutSession(id=session.id, url=session.url or "", provider=self.id)
            except ImportError:
                pass
            except Exception as e:
                if self.secret_key.startswith("sk_live"):
                    raise
                if os.getenv("ENVIRONMENT") == "production":
                    raise RuntimeError(f"Stripe error: {e}") from e

        session_id = f"cs_test_{uuid.uuid4().hex[:24]}"
        url = f"https://checkout.stripe.com/c/pay/{session_id}#sandbox"
        return CheckoutSession(id=session_id, url=url, provider=self.id)

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        env = os.getenv("ENVIRONMENT", "development").lower()
        if not self.webhook_secret:
            if env == "production":
                return False
            return True
        if not signature:
            return False
        if self.use_sdk:
            try:
                import stripe
                stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
                return True
            except Exception:
                return False
        try:
            expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
            if "v1=" in signature:
                parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p)
                return hmac.compare_digest(parts.get("v1", ""), expected)
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False

    async def handle_webhook(self, payload: bytes, signature: str | None) -> WebhookResult:
        if not self.verify_signature(payload, signature):
            raise ValueError("Invalid webhook signature")
        data = json.loads(payload.decode("utf-8"))
        event_type = data.get("type") or data.get("event_type") or "unknown"
        obj = (data.get("data") or {}).get("object") or data.get("object") or {}
        payment_id = obj.get("id") or data.get("payment_id")
        status = obj.get("status") or data.get("status") or "unknown"
        return WebhookResult(event_type=event_type, payment_id=payment_id, status=status, raw=data)

    async def refund(self, provider_payment_id: str, amount: Money) -> dict:
        self._assert_key_policy()
        return {
            "id": f"re_test_{uuid.uuid4().hex[:16]}",
            "payment_id": provider_payment_id,
            "amount": str(amount.amount),
            "currency": amount.currency,
            "status": "succeeded",
            "sandbox": True,
        }


_stripe: StripePaymentProvider | None = None


def get_stripe() -> StripePaymentProvider:
    global _stripe
    if _stripe is None:
        _stripe = StripePaymentProvider()
    return _stripe
