"""Stripe PaymentProvider — sandbox-oriented.

Does NOT perform real charges in automated tests.
Set STRIPE_SECRET_KEY=sk_test_... for sandbox.
"""
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
        self.secret_key = secret_key or os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self._sandbox = not self.secret_key or self.secret_key.startswith("sk_test")

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutSession:
        session_id = f"cs_test_{uuid.uuid4().hex[:24]}"
        url = f"https://checkout.stripe.com/c/pay/{session_id}#sandbox"
        if self.secret_key and not self.secret_key.startswith("sk_test") and not self.secret_key.startswith("sk_"):
            raise RuntimeError("Live Stripe keys are blocked in this build; use sk_test_ sandbox keys")
        return CheckoutSession(id=session_id, url=url, provider=self.id)

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        if not self.webhook_secret:
            return True
        if not signature:
            return False
        try:
            expected = hmac.new(
                self.webhook_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
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
        obj = data.get("data", {}).get("object") or data.get("object") or {}
        payment_id = obj.get("id") or data.get("payment_id")
        status = obj.get("status") or data.get("status") or "unknown"
        return WebhookResult(
            event_type=event_type,
            payment_id=payment_id,
            status=status,
            raw=data,
        )

    async def refund(self, provider_payment_id: str, amount: Money) -> dict:
        if not self._sandbox and self.secret_key.startswith("sk_live"):
            raise RuntimeError("Live refunds blocked in this build")
        return {
            "id": f"re_test_{uuid.uuid4().hex[:16]}",
            "payment_id": provider_payment_id,
            "amount": str(amount.amount),
            "currency": amount.currency,
            "status": "succeeded",
            "sandbox": True,
        }
