import asyncio
import json

from app.services.yookassa import YooKassaPaymentProvider


def test_fetch_sandbox_payment_id():
    p = YooKassaPaymentProvider(shop_id="shop", secret_key="secret")
    data = asyncio.new_event_loop().run_until_complete(p.fetch_payment("yk_test_abc123"))
    assert data is not None
    assert data["status"] == "succeeded"


def test_handle_webhook_fetches_when_credentials(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    p = YooKassaPaymentProvider(shop_id="shop", secret_key="secret")
    payload = json.dumps({
        "event": "payment.succeeded",
        "object": {"id": "yk_test_xyz", "status": "pending", "metadata": {"order_id": "o1"}},
    }).encode()
    result = asyncio.new_event_loop().run_until_complete(p.handle_webhook(payload, signature=None))
    assert result.payment_id == "yk_test_xyz"
    assert result.status == "succeeded"
    assert result.verified_via_api is True


def test_production_without_secret_rejects(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    p = YooKassaPaymentProvider(shop_id="", secret_key="")
    try:
        asyncio.new_event_loop().run_until_complete(p.handle_webhook(b'{"event":"x"}', signature=None))
        assert False, "expected ValueError"
    except ValueError:
        pass
