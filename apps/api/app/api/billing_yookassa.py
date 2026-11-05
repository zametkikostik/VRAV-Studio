"""YooKassa checkout and webhook routes."""
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


@router.post("/checkout/yookassa")
async def create_checkout_yookassa(body: CheckoutBody, user: CurrentUser, db: DbSession):
    from app.services.pricing import PricingError, resolve_checkout_price
    from app.services.yookassa import YooKassaPaymentProvider, CheckoutRequest as YKReq, Money as YKMoney

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
        currency=priced.currency if priced.currency else "RUB",
        status="pending",
        plan_id=priced.plan_id,
        credits_to_grant=priced.credits_to_grant,
        pricing_kind=priced.kind,
        provider="yookassa",
        snapshot={
            "plan_id": priced.plan_id,
            "plan_name": priced.name,
            "amount": str(priced.amount),
            "currency": priced.currency if priced.currency else "RUB",
            "credits_to_grant": str(priced.credits_to_grant),
            "kind": priced.kind,
            "provider": "yookassa",
        },
    )
    db.add(order)
    await db.flush()
    session = await YooKassaPaymentProvider().create_checkout(
        YKReq(
            organization_id=str(org_id),
            plan_id=priced.plan_id,
            amount=YKMoney(amount=priced.amount, currency=order.currency),
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
        "currency": order.currency,
        "credits_to_grant": str(priced.credits_to_grant),
        "checkout": session.model_dump(),
    }


@router.post("/webhooks/yookassa")
async def yookassa_webhook(request: Request, db: DbSession):
    payload = await request.body()
    signature = request.headers.get("content-hmac") or request.headers.get("x-yookassa-signature")
    from app.services.yookassa import YooKassaPaymentProvider

    try:
        result = await YooKassaPaymentProvider().handle_webhook(payload, signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    payment_id = result.payment_id
    if not payment_id:
        raise HTTPException(status_code=400, detail="missing provider payment id")
    event_type = (result.event_type or "unknown").strip() or "unknown"
    notification_id = f"{payment_id}:{event_type}"

    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "yookassa",
            WebhookEvent.provider_event_id == notification_id,
        )
    )
    prior_ev = existing.scalar_one_or_none()
    if prior_ev is not None and prior_ev.processed_at is not None:
        return {
            "status": "already_processed",
            "event_id": notification_id,
            "payment_id": str(payment_id),
            "event_type": event_type,
            "reason": prior_ev.processing_error or "duplicate_notification",
        }
    if prior_ev is None:
        prior_ev = WebhookEvent(
            id=uuid.uuid4(),
            provider="yookassa",
            provider_event_id=notification_id,
            event_type=event_type,
            payload=result.raw,
            processed_at=None,
            processing_error=None,
        )
        db.add(prior_ev)
        await db.flush()

    def _finish(status: str, reason: str | None, credits_granted: str | None = None):
        prior_ev.processed_at = datetime.now(timezone.utc)
        prior_ev.processing_error = reason if status != "processed" else None
        return {
            "status": status,
            "event_id": notification_id,
            "payment_id": str(payment_id),
            "event_type": event_type,
            "reason": reason,
            "payment_status": result.status,
            "verified_via_api": result.verified_via_api,
            "credits_granted": credits_granted,
        }

    if not result.verified_via_api or result.status != "succeeded":
        await db.flush()
        return _finish("ignored", "not_verified_or_not_succeeded")

    meta = result.metadata or {}
    order = None
    if meta.get("order_id"):
        try:
            order = await load_order_for_update(db, uuid.UUID(str(meta["order_id"])))
        except ValueError:
            order = None
    if order is None:
        await db.flush()
        return _finish("ignored", "order_not_found")

    paid_amount = result.amount
    paid_currency = (result.currency or "").upper()
    if paid_amount is None:
        await db.flush()
        return _finish("ignored", "amount_missing")
    if not paid_currency:
        await db.flush()
        return _finish("ignored", "currency_missing")

    order_amount = Decimal(order.amount)
    order_currency = (order.currency or "RUB").upper()
    if abs(paid_amount - order_amount) > Decimal("0.01"):
        await db.flush()
        return _finish("ignored", "amount_mismatch")
    if paid_currency != order_currency:
        await db.flush()
        return _finish("ignored", "currency_mismatch")

    reason, credits_granted = await grant_paid_order_credits(
        db,
        order=order,
        provider="yookassa",
        provider_payment_id=str(payment_id),
        event_id=notification_id,
        raw_response=result.raw,
    )
    if reason == "granted":
        await db.flush()
        return _finish("processed", None, credits_granted)
    if reason == "order_already_paid":
        await db.flush()
        return _finish("already_processed", "order_already_paid")
    await db.flush()
    return _finish("ignored", reason, None)
