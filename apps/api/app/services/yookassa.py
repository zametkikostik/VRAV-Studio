"""YooKassa PaymentProvider — sandbox with optional API fetch verification."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from decimal import Decimal
from typing import Any

import httpx
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
    verified_via_api: bool = False
    amount: Decimal | None = None
    currency: str | None = None
    metadata: dict[str, Any] | None = None


class YooKassaPaymentProvider:
    id = "yookassa"
    API_BASE = "https://api.yookassa.ru/v3"

    def __init__(self, shop_id: str | None = None, secret_key: str | None = None):
        self.shop_id = shop_id if shop_id is not None else os.getenv("YOOKASSA_SHOP_ID", "")
        self.secret_key = secret_key if secret_key is not None else os.getenv("YOOKASSA_SECRET_KEY", "")
        self._live = os.getenv("YOOKASSA_LIVE", "").lower() in ("1", "true", "yes")

    def _auth_header(self) -> str:
        raw = f"{self.shop_id}:{self.secret_key}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutSession:
        if self._live and self.shop_id and self.secret_key:
            payload = {
                "amount": {"value": f"{req.amount.amount:.2f}", "currency": req.amount.currency},
                "confirmation": {"type": "redirect", "return_url": req.success_url},
                "capture": True,
                "metadata": {"organization_id": req.organization_id, **(req.metadata or {})},
            }
            headers = {
                "Authorization": self._auth_header(),
                "Content-Type": "application/json",
                "Idempotence-Key": str(uuid.uuid4()),
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{self.API_BASE}/payments", json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            return CheckoutSession(
                id=data["id"],
                url=(data.get("confirmation") or {}).get("confirmation_url") or "",
                provider=self.id,
            )
        payment_id = f"yk_test_{uuid.uuid4().hex[:20]}"
        url = f"https://yoomoney.ru/checkout/payments/v2/contract?orderId={payment_id}"
        return CheckoutSession(id=payment_id, url=url, provider=self.id)

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        env = os.getenv("ENVIRONMENT", "development").lower()
        if not self.secret_key:
            if env == "production":
                return False
            return True
        if not signature:
            return True
        expected = hmac.new(self.secret_key.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def fetch_payment(self, payment_id: str) -> dict[str, Any] | None:
        if not (self.shop_id and self.secret_key):
            return None
        if payment_id.startswith("yk_test_"):
            return {
                "id": payment_id,
                "status": "succeeded",
                "amount": {"value": "100.00", "currency": "RUB"},
                "metadata": {},
                "sandbox": True,
            }
        headers = {"Authorization": self._auth_header()}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{self.API_BASE}/payments/{payment_id}", headers=headers)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    async def handle_webhook(self, payload: bytes, signature: str | None = None) -> WebhookResult:
        if not self.verify_signature(payload, signature):
            raise ValueError("Invalid YooKassa webhook signature")
        data = json.loads(payload.decode("utf-8"))
        event_type = data.get("event") or data.get("type") or "unknown"
        obj = data.get("object") or {}
        payment_id = obj.get("id") or data.get("id")
        status = obj.get("status") or "unknown"
        amount = None
        currency = None
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else None
        verified = False

        if payment_id and self.shop_id and self.secret_key:
            fetched = await self.fetch_payment(str(payment_id))
            if fetched:
                verified = True
                status = fetched.get("status") or status
                amt = fetched.get("amount") or {}
                try:
                    if amt.get("value") is not None:
                        amount = Decimal(str(amt["value"]))
                    currency = amt.get("currency")
                except Exception:
                    pass
                if isinstance(fetched.get("metadata"), dict):
                    metadata = fetched["metadata"]
                data = {**data, "fetched_payment": fetched}

        return WebhookResult(
            event_type=event_type,
            payment_id=str(payment_id) if payment_id else None,
            status=status,
            raw=data,
            verified_via_api=verified,
            amount=amount,
            currency=currency,
            metadata=metadata,
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
