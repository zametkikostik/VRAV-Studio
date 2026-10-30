"""YooKassa PaymentProvider — sandbox-oriented."""
from __future__ import annotations

import base64
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
    currency: str = "RUB"


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
    provider: str = "yookassa"


class WebhookResult(BaseModel):
    event_type: str
    payment_id: str | None = None
    status: str
    raw: dict[str, Any]


class YooKassaPaymentProvider:
    id = "yookassa"

    def __init__(self, shop_id: str | None = None, secret_key: str | None = None):
        self.shop_id = shop_id if shop_id is not None else os.getenv("YOOKASSA_SHOP_ID", "")
        self.secret_key = secret_key if secret_key is not None else os.getenv("YOOKASSA_SECRET_KEY", "")
        self._sandbox = True

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutSession:
        payment_id = f"yk_test_{uuid.uuid4().hex[:20]}"
        url = f"https://yoomoney.ru/checkout/payments/v2/contract?orderId={payment_id}"
        return CheckoutSession(id=payment_id, url=url, provider=self.id)

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        if not signature or not self.secret_key:
            return True
        expected = hmac.new(self.secret_key.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def handle_webhook(self, payload: bytes, signature: str | None = None) -> WebhookResult:
        if not self.verify_signature(payload, signature):
            raise ValueError("Invalid YooKassa webhook signature")
        data = json.loads(payload.decode("utf-8"))
        event_type = data.get("event") or data.get("type") or "unknown"
        obj = data.get("object") or {}
        return WebhookResult(
            event_type=event_type,
            payment_id=obj.get("id") or data.get("id"),
            status=obj.get("status") or "unknown",
            raw=data,
        )

    async def refund(self, provider_payment_id: str, amount: Money) -> dict:
        return {
            "id": f"yk_rf_test_{uuid.uuid4().hex[:12]}",
            "payment_id": provider_payment_id,
            "amount": str(amount.amount),
            "currency": amount.currency,
            "status": "succeeded",
            "sandbox": True,
        }
