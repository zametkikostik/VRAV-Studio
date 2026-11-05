"""Iter8/10: immutable order snapshot + grant helper (no live payments).

Source checks assert checkout persistence and shared grant/lock wiring.
Missing-snapshot protection lives in billing_grant (not as a literal in API handlers).
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.billing_grant import grant_paid_order_credits, snapshot_credits

API = Path(__file__).resolve().parents[1] / "app" / "api"
GRANT = Path(__file__).resolve().parents[1] / "app" / "services" / "billing_grant.py"


def test_migration_014_exists():
    mig = Path(__file__).resolve().parents[3] / "infra/alembic/versions/014_order_checkout_snapshot.py"
    assert mig.exists()
    body = mig.read_text()
    assert "credits_to_grant" in body
    assert "013" in body


def test_checkout_persists_snapshot_fields_in_source():
    stripe = (API / "billing_checkout.py").read_text()
    yk = (API / "billing_yookassa.py").read_text()

    # Checkout freezes plan/amount/credits/provider on the Order
    for src in (stripe, yk):
        assert "credits_to_grant=priced.credits_to_grant" in src
        assert "pricing_kind=priced.kind" in src
        assert "snapshot={" in src
        assert '"plan_id"' in src or "'plan_id'" in src
        assert "load_order_for_update" in src
        assert "grant_paid_order_credits" in src
        assert "amount_missing" in src
        assert "currency_missing" in src
        # Generic outcome path: rejected grant reasons are ignored, not processed
        assert 'return _finish("ignored", reason' in src
        assert 'return _finish("processed"' in src

    assert 'provider="stripe"' in stripe
    assert 'provider="yookassa"' in yk

    # Webhook must not re-price at grant time
    wh = stripe.find("async def stripe_webhook")
    assert wh > 0
    assert "resolve_checkout_price" not in stripe[wh:]

    ywh = yk.find("async def yookassa_webhook")
    assert ywh > 0
    assert "resolve_checkout_price" not in yk[ywh:]


def test_missing_snapshot_protection_in_grant_helper_source():
    """Missing-snapshot is enforced in the shared grant helper (Iter10)."""
    grant_src = GRANT.read_text()
    assert 'return "missing_snapshot", None' in grant_src
    assert "snapshot_credits" in grant_src


def test_snapshot_credits_none_for_legacy_order():
    order = SimpleNamespace(credits_to_grant=None)
    assert snapshot_credits(order) is None


def test_snapshot_credits_reads_frozen_value():
    order = SimpleNamespace(credits_to_grant=Decimal("100.0000"))
    assert snapshot_credits(order) == Decimal("100.0000")


def test_grant_skips_without_snapshot():
    """Legacy order without credits_to_grant: no Payment, no paid status, no credits."""
    order = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        amount=Decimal("10"),
        currency="USD",
        credits_to_grant=None,
        plan_id=None,
        status="pending",
    )
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def _run():
        return await grant_paid_order_credits(
            db,
            order=order,
            provider="stripe",
            provider_payment_id="pi_x",
            event_id="evt_x",
            raw_response={},
        )

    reason, granted = asyncio.run(_run())
    assert reason == "missing_snapshot"
    assert granted is None
    assert order.status == "pending"
    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_grant_rejects_zero_amount_before_payment():
    order = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        amount=Decimal("0"),
        currency="USD",
        credits_to_grant=Decimal("100"),
        plan_id="credits_100",
        status="pending",
    )
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()

    reason, granted = asyncio.run(
        grant_paid_order_credits(
            db,
            order=order,
            provider="stripe",
            provider_payment_id="pi_zero",
            event_id="evt_zero",
            raw_response={},
        )
    )
    assert reason == "invalid_amount"
    assert granted is None
    assert order.status == "pending"
    db.add.assert_not_called()
