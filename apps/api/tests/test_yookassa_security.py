from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from unittest.mock import patch

from app.services.yookassa import YooKassaPaymentProvider


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_yk_test_id_rejected_in_production():
    with patch.dict(os.environ, {"ENVIRONMENT": "production", "YOOKASSA_SHOP_ID": "shop", "YOOKASSA_SECRET_KEY": "sec"}):
        p = YooKassaPaymentProvider(shop_id="shop", secret_key="sec")
        payload = json.dumps(
            {"event": "payment.succeeded", "object": {"id": "yk_test_abc", "status": "succeeded"}}
        ).encode()
        result = _run(p.handle_webhook(payload, None))
        assert result.status == "rejected"
        assert result.verified_via_api is False


def test_production_requires_credentials_for_webhook():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = YooKassaPaymentProvider(shop_id="", secret_key="")
        payload = json.dumps({"event": "payment.succeeded", "object": {"id": "real-id"}}).encode()
        try:
            _run(p.handle_webhook(payload, None))
            assert False, "expected ValueError"
        except ValueError as e:
            assert "credentials" in str(e).lower()


def test_fetch_yk_test_never_succeeded_in_production():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        p = YooKassaPaymentProvider(shop_id="s", secret_key="k")
        fetched = _run(p.fetch_payment("yk_test_xyz"))
        assert fetched is None


def test_webhook_body_status_not_trusted_without_fetch():
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        p = YooKassaPaymentProvider(shop_id="", secret_key="")
        payload = json.dumps(
            {
                "event": "payment.succeeded",
                "object": {
                    "id": "pay_no_fetch",
                    "status": "succeeded",
                    "amount": {"value": "9999.00", "currency": "RUB"},
                },
            }
        ).encode()
        result = _run(p.handle_webhook(payload, None))
        assert result.verified_via_api is False
        assert result.status == "rejected"


def test_verified_fetch_sets_amount_from_api():
    async def fake_fetch(self, payment_id: str):
        return {
            "id": payment_id,
            "status": "succeeded",
            "amount": {"value": "10.00", "currency": "RUB"},
            "metadata": {"order_id": "11111111-1111-1111-1111-111111111111", "plan_id": "credits_100"},
        }

    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        p = YooKassaPaymentProvider(shop_id="s", secret_key="k")
        with patch.object(YooKassaPaymentProvider, "fetch_payment", fake_fetch):
            payload = json.dumps(
                {"event": "payment.succeeded", "object": {"id": "pay_real", "status": "pending"}}
            ).encode()
            result = _run(p.handle_webhook(payload, None))
            assert result.verified_via_api is True
            assert result.status == "succeeded"
            assert result.amount == Decimal("10.00")
            assert result.currency == "RUB"
