"""Iteration 1 P0 security regression tests."""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_p0a_production_rejects_default_secret():
    from app.main import _assert_production_secrets

    s = SimpleNamespace(
        environment="production",
        secret_key="dev-secret-change-me",
        encryption_key="",
        license_signing_key="",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _assert_production_secrets(s)


def test_p0a_production_rejects_short_secret():
    from app.main import _assert_production_secrets

    s = SimpleNamespace(
        environment="production",
        secret_key="short",
        encryption_key="",
        license_signing_key="",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _assert_production_secrets(s)


def test_p0a_production_accepts_strong_secret():
    from app.main import _assert_production_secrets

    s = SimpleNamespace(
        environment="production",
        secret_key="x" * 32,
        encryption_key="",
        license_signing_key="",
    )
    _assert_production_secrets(s)


def test_p0a_development_allows_default():
    from app.main import _assert_production_secrets

    s = SimpleNamespace(
        environment="development",
        secret_key="dev-secret-change-me",
        encryption_key="",
        license_signing_key="",
    )
    _assert_production_secrets(s)


def test_p0b_staging_without_webhook_secret_rejects():
    from app.services.payment import StripePaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "staging"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="")
        assert p.verify_signature(b'{"type":"x"}', None) is False


def test_p0b_development_without_webhook_secret_allows():
    from app.services.payment import StripePaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="")
        assert p.verify_signature(b'{"type":"x"}', None) is True


def test_p0c_production_no_sdk_raises_on_checkout():
    from app.services.payment import StripePaymentProvider, CheckoutRequest, Money

    with patch.dict(os.environ, {"ENVIRONMENT": "production", "STRIPE_USE_SDK": ""}, clear=False):
        p = StripePaymentProvider(secret_key="", webhook_secret="")
        req = CheckoutRequest(
            organization_id="o",
            plan_id="starter",
            amount=Money(amount=Decimal("10"), currency="USD"),
            success_url="https://x",
            cancel_url="https://y",
        )
        with pytest.raises(RuntimeError, match="SDK required"):
            asyncio.run(p.create_checkout(req))


def test_p0c_dev_sandbox_session_without_keys():
    from app.services.payment import StripePaymentProvider, CheckoutRequest, Money

    with patch.dict(os.environ, {"ENVIRONMENT": "development", "STRIPE_USE_SDK": ""}, clear=False):
        p = StripePaymentProvider(secret_key="", webhook_secret="")
        req = CheckoutRequest(
            organization_id="o",
            plan_id="starter",
            amount=Money(amount=Decimal("10"), currency="USD"),
            success_url="https://x",
            cancel_url="https://y",
        )
        sess = asyncio.run(p.create_checkout(req))
        assert sess.id.startswith("cs_test_")


def test_p0d_billing_locks_order_row():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/api/billing.py").read_text()
    assert "order_already_paid" in text
    assert "with_for_update" in text or "uq_payment_order_succeeded" in (
        Path(__file__).resolve().parents[3] / "infra/alembic/versions/010_one_succeeded_payment_per_order.py"
    ).read_text()


def test_p0d_migration_partial_unique_exists():
    from pathlib import Path

    mig = Path(__file__).resolve().parents[3] / "infra/alembic/versions/010_one_succeeded_payment_per_order.py"
    assert mig.exists()
    body = mig.read_text()
    assert "uq_payment_order_succeeded" in body


def test_p0e_xff_ignored_when_trust_proxy_false():
    from app.api.auth import _client_key
    from app.core.config import get_settings

    get_settings.cache_clear()
    with patch.dict(os.environ, {"TRUST_PROXY_HEADERS": "false"}, clear=False):
        get_settings.cache_clear()
        req = MagicMock()
        req.headers.get = lambda k, default=None: "9.9.9.9" if k.lower() == "x-forwarded-for" else default
        req.client.host = "1.2.3.4"
        assert _client_key(req) == "1.2.3.4"
    get_settings.cache_clear()


def test_p0e_xff_honored_when_trust_proxy_true():
    from app.api.auth import _client_key
    from app.core.config import get_settings

    get_settings.cache_clear()
    with patch.dict(
        os.environ,
        {"TRUST_PROXY_HEADERS": "true", "TRUSTED_PROXIES": "10.0.0.0/8,127.0.0.1"},
        clear=False,
    ):
        get_settings.cache_clear()
        req = MagicMock()
        req.headers.get = lambda k, default=None: "9.9.9.9" if k.lower() == "x-forwarded-for" else default
        req.client.host = "10.0.0.5"
        assert _client_key(req) == "9.9.9.9"
    get_settings.cache_clear()


def test_p2b_storage_rejects_path_escape():
    from app.services.storage import LocalStorageProvider

    p = LocalStorageProvider(root="/tmp/vrav-storage-test-root")
    with pytest.raises(ValueError, match="escapes"):
        p._path("../../etc/passwd")
