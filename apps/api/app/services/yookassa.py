"""YooKassa PaymentProvider — production uses API fetch only; yk_test never succeeds in prod."""
from __future__ import annotations

import base64
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


def _env() -> str:
    return os.getenv("ENVIRONMENT", "development").lower()


def _is_production() -> bool:
    return _env() == "production"


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

    def credentials_ready(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutSession:
        if _is_production() and not self.credentials_ready():
            raise RuntimeError("YooKassa credentials required in production")
        if self._live and self.credentials_ready():
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
        if _is_production():
            raise RuntimeError("YooKassa live checkout required in production (set YOOKASSA_LIVE=1)")
        payment_id = f"yk_test_{uuid.uuid4().hex[:20]}"
        url = f"https://yoomoney.ru/checkout/payments/v2/contract?orderId={payment_id}"
        return CheckoutSession(id=payment_id, url=url, provider=self.id)

    async def fetch_payment(self, payment_id: str) -> dict[str, Any] | None:
        pid = str(payment_id)
        if pid.startswith("yk_test_"):
            if _is_production():
                return None
            return {
                "id": pid,
                "status": "pending",
                "amount": {"value": "0.00", "currency": "RUB"},
                "metadata": {},
                "sandbox": True,
            }
        if not self.credentials_ready():
            return None
        headers = {"Authorization": self._auth_header()}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{self.API_BASE}/payments/{pid}", headers=headers)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    async def handle_webhook(self, payload: bytes, signature: str | None = None) -> WebhookResult:
        if _is_production() and not self.credentials_ready():
            raise ValueError("YooKassa credentials required to process webhooks in production")

        data = json.loads(payload.decode("utf-8"))
        event_type = data.get("event") or data.get("type") or "unknown"
        obj = data.get("object") or {}
        payment_id = obj.get("id") or data.get("id")
        status = "unknown"
        amount = None
        currency = None
        metadata = None
        verified = False

        if not payment_id:
            return WebhookResult(
                event_type=event_type, payment_id=None, status="rejected", raw=data, verified_via_api=False
            )

        pid = str(payment_id)
        if pid.startswith("yk_test_") and _is_production():
            return WebhookResult(
                event_type=event_type, payment_id=pid, status="rejected", raw=data, verified_via_api=False
            )

        fetched = await self.fetch_payment(pid)
        if not fetched:
            return WebhookResult(
                event_type=event_type, payment_id=pid, status="rejected", raw=data, verified_via_api=False
            )

        if fetched.get("sandbox"):
            return WebhookResult(
                event_type=event_type,
                payment_id=pid,
                status=str(fetched.get("status") or "pending"),
                raw={**data, "fetched_payment": fetched},
                verified_via_api=False,
                amount=Decimal(str((fetched.get("amount") or {}).get("value") or "0")),
                currency=(fetched.get("amount") or {}).get("currency"),
            )

        verified = True
        status = str(fetched.get("status") or "unknown")
        amt = fetched.get("amount") or {}
        try:
            if amt.get("value") is not None:
                amount = Decimal(str(amt["value"]))
            currency = amt.get("currency")
        except Exception:
            amount = None
            currency = None
        if isinstance(fetched.get("metadata"), dict):
            metadata = fetched["metadata"]

        return WebhookResult(
            event_type=event_type,
            payment_id=pid,
            status=status,
            raw={**data, "fetched_payment": fetched},
            verified_via_api=verified,
            amount=amount,
            currency=currency,
            metadata=metadata,
        )

    async def refund(self, provider_payment_id: str, amount: Money) -> dict:
        if _is_production() and not self.credentials_ready():
            raise RuntimeError("YooKassa credentials required for refunds in production")
        return {
            "id": f"yk_rf_test_{uuid.uuid4().hex[:12]}",
            "payment_id": provider_payment_id,
            "amount": str(amount.amount),
            "currency": amount.currency,
            "status": "pending",
            "sandbox": True,
        }
