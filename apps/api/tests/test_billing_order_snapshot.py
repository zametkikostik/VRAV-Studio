"""Iter8: immutable order snapshot + grant helper (no live payments)."""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.billing_grant import grant_paid_order_credits, snapshot_credits


def test_migration_014_exists():
    mig = Path(__file__).resolve().parents[3] / "infra/alembic/versions/014_order_checkout_snapshot.py"
    assert mig.exists()
    body = mig.read_text()
    assert "credits_to_grant" in body
    assert "013" in body


def test_checkout_persists_snapshot_fields_in_source():
    api = Path(__file__).resolve().parents[1] / "app" / "api"
    stripe = (api / "billing_checkout.py").read_text()
    yk = (api / "billing_yookassa.py").read_text()
    assert "credits_to_grant=priced.credits_to_grant" in stripe
    assert "credits_to_grant=priced.credits_to_grant" in yk
    assert "load_order_for_update" in stripe and "load_order_for_update" in yk
    assert "missing_snapshot" in stripe and "missing_snapshot" in yk
    assert "amount_missing" in stripe and "amount_missing" in yk
    assert "currency_missing" in stripe
    assert "grant_paid_order_credits" in stripe
    assert "grant_paid_order_credits" in yk
    wh = stripe.find("async def stripe_webhook")
    assert wh > 0
    assert "resolve_checkout_price" not in stripe[wh:]


def test_snapshot_credits_none_for_legacy_order():
    order = SimpleNamespace(credits_to_grant=None)
    assert snapshot_credits(order) is None


def test_snapshot_credits_reads_frozen_value():
    order = SimpleNamespace(credits_to_grant=Decimal("100.0000"))
    assert snapshot_credits(order) == Decimal("100.0000")


def test_grant_skips_without_snapshot():
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
    prior = MagicMock()
    prior.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=prior)

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
