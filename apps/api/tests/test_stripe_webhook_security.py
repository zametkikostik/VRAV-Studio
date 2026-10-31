from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

from app.services.payment import StripePaymentProvider


def test_production_rejects_missing_secret():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="")
        assert p.verify_signature(b'{"type":"x"}', "t=1,v1=abc") is False


def test_production_rejects_missing_signature():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="whsec_test")
        assert p.verify_signature(b'{"type":"x"}', None) is False


def test_production_rejects_without_stripe_sdk_construct():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="whsec_test")
        assert p.verify_signature(b'{"type":"checkout.session.completed"}', "t=1,v1=deadbeef") is False


def test_handle_webhook_raises_on_bad_sig_production():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="whsec_test")
        try:
            asyncio.new_event_loop().run_until_complete(p.handle_webhook(b'{"type":"x"}', "bad"))
            assert False
        except ValueError as e:
            assert "signature" in str(e).lower() or "secret" in str(e).lower()
