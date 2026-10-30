import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.billing import (
    Order,
    Payment,
    TariffPlan,
    WebhookEvent,
)
from app.models.organization import OrganizationMember
from app.services.credits import CreditService
from app.services.entitlement import EntitlementService
from app.services.payment import CheckoutRequest, Money, get_stripe

router = APIRouter(prefix="/billing", tags=["billing"])


class TopupRequest(BaseModel):
    organization_id: str
    amount: Decimal = Field(gt=0, decimal_places=4)


class CheckoutBody(BaseModel):
    organization_id: str
    plan_id: str | None = None
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    success_url: str = "https://localhost/success"
    cancel_url: str = "https://localhost/cancel"


async def _require_member(db: DbSession, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    r = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of organization")


@router.get("/plans")
async def list_plans(db: DbSession):
    result = await db.execute(select(TariffPlan).where(TariffPlan.is_active.is_(True)))
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "price_monthly": str(p.price_monthly),
            "currency": p.currency,
            "included_credits": str(p.included_credits),
            "features": p.features,
        }
        for p in plans
    ]


@router.get("/credits/{organization_id}")
async def get_credits(organization_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _require_member(db, user.id, organization_id)
    svc = CreditService(db)
    account = await svc.get_or_create_account(organization_id)
    return {
        "organization_id": str(organization_id),
        "balance": str(account.balance),
        "reserved": str(account.reserved),
        "available": str(account.balance - account.reserved),
    }


@router.post("/credits/topup")
async def topup_credits(body: TopupRequest, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_member(db, user.id, org_id)
    svc = CreditService(db)
    account = await svc.topup(org_id, body.amount, description="manual_topup")
    return {"balance": str(account.balance), "reserved": str(account.reserved)}


@router.post("/checkout")
async def create_checkout(body: CheckoutBody, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_member(db, user.id, org_id)

    order = Order(
        id=uuid.uuid4(),
        organization_id=org_id,
        amount=body.amount,
        currency=body.currency,
        status="pending",
    )
    db.add(order)
    await db.flush()

    stripe = get_stripe()
    session = await stripe.create_checkout(
        CheckoutRequest(
            organization_id=str(org_id),
            plan_id=body.plan_id,
            amount=Money(amount=body.amount, currency=body.currency),
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"order_id": str(order.id)},
        )
    )
    return {"order_id": str(order.id), "checkout": session.model_dump()}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: DbSession):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    stripe = get_stripe()
    try:
        result = await stripe.handle_webhook(payload, signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_id = result.raw.get("id") or result.payment_id or f"evt_{uuid.uuid4().hex[:16]}"
    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "stripe",
            WebhookEvent.provider_event_id == event_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": event_id}

    wh = WebhookEvent(
        id=uuid.uuid4(),
        provider="stripe",
        provider_event_id=event_id,
        event_type=result.event_type,
        payload=result.raw,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(wh)

    if result.event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        if result.payment_id:
            pay = Payment(
                id=uuid.uuid4(),
                order_id=uuid.uuid4(),
                provider="stripe",
                provider_payment_id=result.payment_id,
                amount=Decimal("0"),
                currency="USD",
                status=result.status or "succeeded",
                raw_response=result.raw,
            )
            dup = await db.execute(
                select(Payment).where(
                    Payment.provider == "stripe",
                    Payment.provider_payment_id == result.payment_id,
                )
            )
            if dup.scalar_one_or_none() is None:
                try:
                    meta = (result.raw.get("data") or {}).get("object") or {}
                    order_id_str = (meta.get("metadata") or {}).get("order_id")
                    if order_id_str:
                        pay.order_id = uuid.UUID(order_id_str)
                        db.add(pay)
                except Exception:
                    pass

    await db.flush()
    return {"status": "processed", "event_id": event_id, "event_type": result.event_type}


@router.get("/entitlements/{organization_id}")
async def entitlements(organization_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _require_member(db, user.id, organization_id)
    ent = EntitlementService(db)
    sub = await ent.get_active_subscription(organization_id)
    credits = await ent.available_credits(organization_id)
    return {
        "organization_id": str(organization_id),
        "subscription": {"plan_id": sub.plan_id, "status": sub.status} if sub else None,
        "available_credits": str(credits),
    }


@router.post("/checkout/yookassa")
async def create_checkout_yookassa(body: CheckoutBody, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_member(db, user.id, org_id)

    order = Order(
        id=uuid.uuid4(),
        organization_id=org_id,
        amount=body.amount,
        currency=body.currency if body.currency else "RUB",
        status="pending",
    )
    db.add(order)
    await db.flush()

    from app.services.yookassa import YooKassaPaymentProvider, CheckoutRequest as YKReq, Money as YKMoney

    yk = YooKassaPaymentProvider()
    session = await yk.create_checkout(
        YKReq(
            organization_id=str(org_id),
            plan_id=body.plan_id,
            amount=YKMoney(amount=body.amount, currency=order.currency),
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"order_id": str(order.id)},
        )
    )
    return {"order_id": str(order.id), "checkout": session.model_dump()}


@router.post("/webhooks/yookassa")
async def yookassa_webhook(request: Request, db: DbSession):
    payload = await request.body()
    signature = request.headers.get("content-hmac") or request.headers.get("x-yookassa-signature")
    from app.services.yookassa import YooKassaPaymentProvider

    yk = YooKassaPaymentProvider()
    try:
        result = await yk.handle_webhook(payload, signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_id = result.raw.get("event_id") or result.payment_id or f"yk_evt_{uuid.uuid4().hex[:16]}"
    if isinstance(event_id, dict):
        event_id = str(uuid.uuid4())
    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "yookassa",
            WebhookEvent.provider_event_id == str(event_id),
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": str(event_id)}

    wh = WebhookEvent(
        id=uuid.uuid4(),
        provider="yookassa",
        provider_event_id=str(event_id),
        event_type=result.event_type,
        payload=result.raw,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(wh)
    await db.flush()
    return {"status": "processed", "event_id": str(event_id), "event_type": result.event_type}
