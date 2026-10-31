"""Iteration 0 — regression checks for all P0 security commits.

Covers:
  P0.1 YooKassa — no fake credits / yk_test rejected in production
  P0.2 License  — paid order gate + server-side plan caps
  P0.3 Stripe   — production fail-closed signature verification
  P0.4 Amount   — Decimal money, no float in pricing helpers where present
  P0.5 Render   — jobs.py never blocks on get() or inline render_timeline()
  P0.6 WS       — auth before accept, membership required
  P0.7 Credits  — stream finally release + release_stale_reservations
"""
from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


def test_p01_yk_test_rejected_in_production():
    from app.services.yookassa import YooKassaPaymentProvider

    with patch.dict(
        os.environ,
        {"ENVIRONMENT": "production", "YOOKASSA_SHOP_ID": "shop", "YOOKASSA_SECRET_KEY": "sec"},
    ):
        p = YooKassaPaymentProvider(shop_id="shop", secret_key="sec")
        payload = json.dumps(
            {"event": "payment.succeeded", "object": {"id": "yk_test_abc", "status": "succeeded"}}
        ).encode()
        result = asyncio.new_event_loop().run_until_complete(p.handle_webhook(payload, None))
        assert result.status == "rejected"
        assert result.verified_via_api is False


def test_p01_production_requires_credentials():
    from app.services.yookassa import YooKassaPaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        p = YooKassaPaymentProvider(shop_id="", secret_key="")
        with pytest.raises(ValueError, match="[Cc]redential"):
            asyncio.new_event_loop().run_until_complete(
                p.handle_webhook(b'{"event":"x","object":{"id":"pay1"}}', None)
            )


def test_p01_sandbox_stub_is_pending_not_succeeded():
    from app.services.yookassa import YooKassaPaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        p = YooKassaPaymentProvider(shop_id="s", secret_key="k")
        data = asyncio.new_event_loop().run_until_complete(p.fetch_payment("yk_test_xyz"))
        assert data is not None
        assert data["status"] == "pending"
        assert data.get("sandbox") is True


def test_p01_webhook_body_status_not_trusted_without_api_fetch():
    from app.services.yookassa import YooKassaPaymentProvider

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
        result = asyncio.new_event_loop().run_until_complete(p.handle_webhook(payload, None))
        assert result.verified_via_api is False
        assert result.status == "rejected"


def test_p02_plan_caps_bound_and_unknown_defaults():
    from app.services.license_policy import PLAN_CAPS, resolve_plan_caps

    assert PLAN_CAPS["selfhosted"]["max_installations"] <= 3
    pid, n, feat = resolve_plan_caps("hacked_unlimited")
    assert pid == "selfhosted"
    assert n <= 3
    assert feat.get("desktop") is True


def test_p02_admin_issue_flag_default_off():
    from app.services.license_policy import allow_admin_license_issue

    with patch.dict(os.environ, {"ALLOW_ADMIN_LICENSE_ISSUE": ""}, clear=False):
        assert allow_admin_license_issue() is False


def test_p02_issue_endpoint_requires_order_or_admin_flag():
    text = (API_ROOT / "app" / "api" / "license.py").read_text()
    assert "order_id" in text
    assert "ALLOW_ADMIN_LICENSE_ISSUE" in text or "allow_admin_license_issue" in text
    assert "resolve_plan_caps" in text or "PLAN_CAPS" in text
    assert "402" in text or "not paid" in text.lower() or "Order is not paid" in text


def test_p03_production_rejects_missing_secret():
    from app.services.payment import StripePaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="")
        assert p.verify_signature(b'{"type":"x"}', "t=1,v1=abc") is False


def test_p03_production_rejects_missing_signature():
    from app.services.payment import StripePaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="whsec_test")
        assert p.verify_signature(b'{"type":"x"}', None) is False


def test_p03_production_rejects_invalid_signature_string():
    from app.services.payment import StripePaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="whsec_test")
        assert p.verify_signature(b'{"type":"checkout.session.completed"}', "t=1,v1=deadbeef") is False


def test_p03_handle_webhook_raises_on_bad_sig_production():
    from app.services.payment import StripePaymentProvider

    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        p = StripePaymentProvider(secret_key="sk_test_x", webhook_secret="whsec_test")
        with pytest.raises(ValueError):
            asyncio.new_event_loop().run_until_complete(p.handle_webhook(b'{"type":"x"}', "bad"))


def test_p03_uses_construct_event_in_source():
    text = (API_ROOT / "app" / "services" / "payment.py").read_text()
    assert "construct_event" in text
    assert "ENVIRONMENT" in text


def test_p04_money_uses_decimal_not_float():
    from app.services.payment import Money as StripeMoney
    from app.services.yookassa import Money as YkMoney

    m1 = StripeMoney(amount=Decimal("9.99"), currency="USD")
    m2 = YkMoney(amount=Decimal("100.00"), currency="RUB")
    assert isinstance(m1.amount, Decimal)
    assert isinstance(m2.amount, Decimal)
    assert not isinstance(m1.amount, float)


def test_p04_pricing_module_uses_decimal_if_present():
    pricing = API_ROOT / "app" / "services" / "pricing.py"
    if not pricing.exists():
        pytest.skip("pricing.py not present")
    text = pricing.read_text()
    assert "Decimal" in text


def test_p05_jobs_no_async_result_get():
    text = (API_ROOT / "app" / "api" / "jobs.py").read_text()
    assert "async_result.get" not in text


def test_p05_jobs_no_inline_render_timeline():
    text = (API_ROOT / "app" / "api" / "jobs.py").read_text()
    assert text.count("render_timeline(") == 0


def test_p05_jobs_celery_unavailable_returns_503_path():
    text = (API_ROOT / "app" / "api" / "jobs.py").read_text()
    assert "Render worker unavailable" in text or "celery_unavailable" in text
    assert "503" in text
    assert "vrav.media.render" in text


def test_p06_ws_auth_before_accept():
    text = (API_ROOT / "app" / "api" / "ws_collab.py").read_text()
    assert "_authorize_room" in text
    assert "decode_access_token" in text
    assert text.find("await _authorize_room") < text.find("await websocket.accept()")
    assert "4401" in text


def test_p06_ws_membership_check():
    text = (API_ROOT / "app" / "api" / "ws_collab.py").read_text()
    assert "OrganizationMember" in text
    assert "project.organization_id" in text or "organization_id" in text


def test_p07_stream_has_settled_finally_release():
    text = (API_ROOT / "app" / "api" / "ai.py").read_text()
    assert "settled" in text
    assert "finally:" in text
    assert text.count("credit_svc.release") >= 1


def test_p07_release_stale_reservations_exists():
    credits = API_ROOT / "app" / "services" / "credits.py"
    stale = API_ROOT / "app" / "services" / "credits_stale.py"
    text = credits.read_text() if credits.exists() else ""
    stale_text = stale.read_text() if stale.exists() else ""
    combined = text + stale_text
    assert "release_stale" in combined or "release_stale_reservations" in combined


def test_p07_commit_and_release_idempotent_status_guards():
    text = (API_ROOT / "app" / "services" / "credits.py").read_text()
    assert 'status != "pending"' in text or "status != 'pending'" in text
