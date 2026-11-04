"""Stripe checkout and webhook routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.api.billing import CheckoutBody, _require_member, router
from app.api.deps import CurrentUser, DbSession
from app.models.billing import Order, Payment, WebhookEvent
from app.services.credits import CreditService
from app.services.payment import CheckoutRequest, Money, get_stripe


@router.post("/checkout")
async def create_checkout(body: CheckoutBody, user: CurrentUser, db: DbSession):
    from app.services.pricing import PricingError, resolve_checkout_price

    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_member(db, user.id, org_id)
    try:
        priced = await resolve_checkout_price(
            db, plan_id=body.plan_id, client_amount=body.amount, client_currency=body.currency
        )
    except PricingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    order = Order(
        id=uuid.uuid4(),
        organization_id=org_id,
        amount=priced.amount,
        currency=priced.currency,
        status="pending",
    )
    db.add(order)
    await db.flush()
    session = await get_stripe().create_checkout(
        CheckoutRequest(
            organization_id=str(org_id),
            plan_id=priced.plan_id,
            amount=Money(amount=priced.amount, currency=priced.currency),
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={
                "order_id": str(order.id),
                "plan_id": priced.plan_id,
                "credits_to_grant": str(priced.credits_to_grant),
            },
        )
    )
    return {
        "order_id": str(order.id),
        "plan_id": priced.plan_id,
        "amount": str(priced.amount),
        "currency": priced.currency,
        "credits_to_grant": str(priced.credits_to_grant),
        "checkout": session.model_dump(),
    }


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: DbSession):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        result = await get_stripe().handle_webhook(payload, signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    event_id = result.raw.get("id") or result.payment_id or f"evt_{uuid.uuid4().hex[:16]}"
    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "stripe", WebhookEvent.provider_event_id == event_id
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": event_id}
    db.add(
        WebhookEvent(
            id=uuid.uuid4(),
            provider="stripe",
            provider_event_id=event_id,
            event_type=result.event_type,
            payload=result.raw,
            processed_at=datetime.now(timezone.utc),
        )
    )
    credits_granted = None
    if result.event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        obj = (result.raw.get("data") or {}).get("object") or {}
        meta = obj.get("metadata") or {}
        pay_status = (obj.get("payment_status") or obj.get("status") or result.status or "").lower()
        if pay_status not in ("paid", "succeeded", "complete", "completed"):
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "not_paid",
                "payment_status": pay_status,
                "credits_granted": None,
            }
        order_id_str = meta.get("order_id")
        provider_payment_id = result.payment_id or obj.get("id") or event_id
        order = None
        if order_id_str:
            try:
                order = await db.get(Order, uuid.UUID(order_id_str))
            except ValueError:
                order = None
        if order is None:
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "order_not_found",
                "credits_granted": None,
            }
        paid_amount = None
        paid_currency = None
        if obj.get("amount_total") is not None:
            try:
                paid_amount = (Decimal(str(obj["amount_total"])) / Decimal("100")).quantize(Decimal("0.01"))
            except Exception:
                paid_amount = None
        if obj.get("currency"):
            paid_currency = str(obj["currency"]).upper()
        order_amount = Decimal(order.amount)
        order_currency = (order.currency or "USD").upper()
        if paid_amount is not None and abs(paid_amount - order_amount) > Decimal("0.01"):
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "amount_mismatch",
                "credits_granted": None,
            }
        if paid_currency and paid_currency != order_currency:
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "currency_mismatch",
                "credits_granted": None,
            }
        amount = order_amount
        currency = order.currency
        prior = await db.execute(
            select(Payment).where(Payment.order_id == order.id, Payment.status == "succeeded")
        )
        if prior.scalar_one_or_none() is not None:
            order.status = "paid"
            await db.flush()
            return {
                "status": "already_processed",
                "event_id": event_id,
                "reason": "order_already_paid",
                "credits_granted": None,
            }
        order.status = "paid"
        dup = await db.execute(
            select(Payment).where(
                Payment.provider == "stripe",
                Payment.provider_payment_id == str(provider_payment_id),
            )
        )
        if dup.scalar_one_or_none() is None and amount > 0:
            db.add(
                Payment(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    provider="stripe",
                    provider_payment_id=str(provider_payment_id),
                    amount=amount,
                    currency=currency,
                    status="succeeded",
                    raw_response=result.raw,
                )
            )
            grant = Decimal("0")
            plan_id = meta.get("plan_id")
            if plan_id:
                try:
                    from app.services.pricing import resolve_checkout_price

                    priced = await resolve_checkout_price(db, plan_id=str(plan_id))
                    grant = Decimal(priced.credits_to_grant)
                except Exception:
                    grant = Decimal("0")
            if grant > 0:
                await CreditService(db).topup(
                    order.organization_id,
                    grant,
                    description=f"stripe:{provider_payment_id}",
                    metadata={
                        "order_id": str(order.id),
                        "event_id": event_id,
                        "plan_id": plan_id,
                    },
                )
                credits_granted = str(grant)
    await db.flush()
    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": result.event_type,
        "credits_granted": credits_granted,
    }
