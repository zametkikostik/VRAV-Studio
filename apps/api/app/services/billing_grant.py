"""Atomic credit grant for paid orders using immutable checkout snapshot."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Order, Payment
from app.services.credits import CreditService


async def load_order_for_update(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    r = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    return r.scalar_one_or_none()


def snapshot_credits(order: Order) -> Decimal | None:
    """Credits frozen at checkout. None => historical order — do not auto-grant."""
    if order.credits_to_grant is None:
        return None
    return Decimal(str(order.credits_to_grant))


async def grant_paid_order_credits(
    db: AsyncSession,
    *,
    order: Order,
    provider: str,
    provider_payment_id: str,
    event_id: str,
    raw_response: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """
    Create succeeded Payment and top up from order.credits_to_grant in one transactional unit.

    Caller must already have locked `order` with FOR UPDATE and verified amount/currency
    against the order snapshot columns.

    Returns (status_reason, credits_granted_str_or_none).
    """
    amount = Decimal(str(order.amount))
    if amount <= 0:
        return "invalid_amount", None

    grant = snapshot_credits(order)
    if grant is None:
        return "missing_snapshot", None
    if grant < 0:
        return "invalid_grant", None

    # Already paid this order?
    prior = await db.execute(
        select(Payment).where(Payment.order_id == order.id, Payment.status == "succeeded")
    )
    if prior.scalar_one_or_none() is not None:
        if order.status != "paid":
            order.status = "paid"
        return "order_already_paid", None

    # Provider payment already recorded (any order)?
    dup = await db.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.provider_payment_id == str(provider_payment_id),
        )
    )
    existing_pay = dup.scalar_one_or_none()
    if existing_pay is not None:
        if existing_pay.order_id == order.id and existing_pay.status == "succeeded":
            if order.status != "paid":
                order.status = "paid"
            return "order_already_paid", None
        # Same payment id must not attach to a different order or re-grant
        return "payment_already_recorded", None

    # Insert payment first; unique constraints enforce single success per order / provider id.
    # Only then mark order paid and grant credits — avoids paid-without-payment.
    db.add(
        Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            provider=provider,
            provider_payment_id=str(provider_payment_id),
            amount=amount,
            currency=order.currency,
            status="succeeded",
            raw_response=raw_response,
        )
    )
    await db.flush()  # surface IntegrityError early inside the request transaction

    order.status = "paid"

    credits_granted = None
    if grant > 0:
        await CreditService(db).topup(
            order.organization_id,
            grant,
            description=f"{provider}:{provider_payment_id}",
            metadata={
                "order_id": str(order.id),
                "event_id": event_id,
                "plan_id": order.plan_id,
                "source": "order_snapshot",
            },
        )
        credits_granted = str(grant)
    return "granted", credits_granted
