"""Iteration 9 P0: grant sequence, YooKassa notification identity, positive amount."""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]


def test_yookassa_notification_id_uses_payment_and_event_type():
    text = (ROOT / "app/api/billing_yookassa.py").read_text()
    assert 'notification_id = f"{payment_id}:{event_type}"' in text
    assert "provider_event_id=notification_id" in text
    assert "provider_event_id=str(event_id)" not in text
    assert "event_id = result.payment_id" not in text


def test_grant_helper_checks_dup_before_paid_status():
    text = (ROOT / "app/services/billing_grant.py").read_text()
    grant_paid = text.rfind('order.status = "paid"')
    assert grant_paid > 0
    assert "payment_already_recorded" in text[:grant_paid]
    assert "if amount <= 0:" in text
    assert "amount <= 0 and grant <= 0" not in text


def test_grant_rejects_non_positive_amount():
    from app.services.billing_grant import grant_paid_order_credits

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
    db.flush = AsyncMock()

    reason, granted = asyncio.run(
        grant_paid_order_credits(
            db,
            order=order,
            provider="stripe",
            provider_payment_id="pi_x",
            event_id="evt_x",
            raw_response={},
        )
    )
    assert reason == "invalid_amount"
    assert granted is None
    assert order.status == "pending"


def test_grant_payment_already_recorded_does_not_mark_paid():
    from app.services.billing_grant import grant_paid_order_credits

    order = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        amount=Decimal("10"),
        currency="USD",
        credits_to_grant=Decimal("100"),
        plan_id="credits_100",
        status="pending",
    )
    other_order_id = uuid.uuid4()

    prior = MagicMock()
    prior.scalar_one_or_none.return_value = None
    dup = MagicMock()
    dup.scalar_one_or_none.return_value = SimpleNamespace(
        order_id=other_order_id, status="succeeded"
    )

    async def execute(stmt):
        if not hasattr(execute, "n"):
            execute.n = 0
        execute.n += 1
        return prior if execute.n == 1 else dup

    db = MagicMock()
    db.execute = execute
    db.add = MagicMock()
    db.flush = AsyncMock()

    reason, granted = asyncio.run(
        grant_paid_order_credits(
            db,
            order=order,
            provider="stripe",
            provider_payment_id="pi_shared",
            event_id="evt",
            raw_response={},
        )
    )
    assert reason == "payment_already_recorded"
    assert granted is None
    assert order.status == "pending"


def test_snapshot_missing_still_blocks_legacy():
    from app.services.billing_grant import grant_paid_order_credits

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
    reason, granted = asyncio.run(
        grant_paid_order_credits(
            db,
            order=order,
            provider="yookassa",
            provider_payment_id="pay_1",
            event_id="pay_1:payment.succeeded",
            raw_response={},
        )
    )
    assert reason == "missing_snapshot"
    assert granted is None
