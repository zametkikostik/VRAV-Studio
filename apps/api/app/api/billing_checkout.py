"""Stripe checkout and webhook routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.api.billing import CheckoutBody, _require_member, router
from app.api.deps import CurrentUser, DbSession
from app.models.billing import Order, WebhookEvent
from app.services.billing_grant import grant_paid_order_credits, load_order_for_update
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
        plan_id=priced.plan_id,
        credits_to_grant=priced.credits_to_grant,
        pricing_kind=priced.kind,
        provider="stripe",
        snapshot={
            "plan_id": priced.plan_id,
            "plan_name": priced.name,
            "amount": str(priced.amount),
            "currency": priced.currency,
            "credits_to_grant": str(priced.credits_to_grant),
            "kind": priced.kind,
            "provider": "stripe",
        },
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
    event_id = result.raw.get("id") if isinstance(result.raw, dict) else None
    if not event_id:
        event_id = result.payment_id
    if not event_id:
        raise HTTPException(status_code=400, detail="missing provider event id")
    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "stripe", WebhookEvent.provider_event_id == str(event_id)
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": event_id}
    db.add(
        WebhookEvent(
            id=uuid.uuid4(),
            provider="stripe",
            provider_event_id=str(event_id),
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
        provider_payment_id = result.payment_id or obj.get("id")
        if not provider_payment_id:
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "missing_payment_id",
                "credits_granted": None,
            }
        order = None
        if order_id_str:
            try:
                order = await load_order_for_update(db, uuid.UUID(order_id_str))
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
        if paid_amount is None:
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "amount_missing",
                "credits_granted": None,
            }
        if not paid_currency:
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "currency_missing",
                "credits_granted": None,
            }
        order_amount = Decimal(order.amount)
        order_currency = (order.currency or "USD").upper()
        if abs(paid_amount - order_amount) > Decimal("0.01"):
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "amount_mismatch",
                "credits_granted": None,
            }
        if paid_currency != order_currency:
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "currency_mismatch",
                "credits_granted": None,
            }
        reason, credits_granted = await grant_paid_order_credits(
            db,
            order=order,
            provider="stripe",
            provider_payment_id=str(provider_payment_id),
            event_id=str(event_id),
            raw_response=result.raw,
        )
        if reason == "order_already_paid":
            await db.flush()
            return {
                "status": "already_processed",
                "event_id": event_id,
                "reason": "order_already_paid",
                "credits_granted": None,
            }
        if reason == "missing_snapshot":
            await db.flush()
            return {
                "status": "ignored",
                "event_id": event_id,
                "reason": "missing_snapshot",
                "credits_granted": None,
            }
    await db.flush()
    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": result.event_type,
        "credits_granted": credits_granted,
    }
