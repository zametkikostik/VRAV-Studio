"""Iteration 0 security regression tests — no live payments."""
from __future__ import annotations

import pytest


def test_stripe_rejects_unsigned_webhook_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    from app.services.payment import StripePaymentProvider

    p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="")
    assert p.verify_signature(b'{"type":"test"}', None) is False
    assert p.verify_signature(b'{"type":"test"}', "t=1,v1=abc") is False


def test_stripe_allows_unsigned_in_development_without_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from app.services.payment import StripePaymentProvider

    p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="")
    assert p.verify_signature(b"{}", None) is True


def test_settings_upload_and_topup_flags():
    from app.core.config import Settings

    s = Settings(environment="production", allow_manual_credit_topup=False, max_upload_bytes=10)
    assert s.environment == "production"
    assert s.allow_manual_credit_topup is False
    assert s.max_upload_bytes == 10


def test_yookassa_rejects_in_production_without_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    from app.services.yookassa import YooKassaPaymentProvider

    p = YooKassaPaymentProvider(shop_id="", secret_key="")
    assert p.verify_signature(b"{}", None) is False


@pytest.mark.asyncio
async def test_topup_blocked_in_production_without_flag(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_MANUAL_CREDIT_TOPUP", "false")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.environment == "production"
    assert settings.allow_manual_credit_topup is False
    get_settings.cache_clear()
