import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.billing import (
    CreditAccount,
    Order,
    Payment,
    Subscription,
    TariffPlan,
    WebhookEvent,
)
from app.models.organization import OrganizationMember
from app.services.credits import CreditService, InsufficientCreditsError
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


async def _require_admin(db: DbSession, user_id: uuid.UUID, org_id: uuid.UUID) -> OrganizationMember:
    r = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    mem = r.scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=403, detail="Not a member of organization")
    if mem.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return mem


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
    """Manual credit grant — disabled in production unless explicitly allowed."""
    from app.core.config import get_settings

    settings = get_settings()
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")

    if settings.environment == "production" and not settings.allow_manual_credit_topup:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manual credit top-up is disabled in production; credits are granted via verified payments",
        )
    if not settings.allow_manual_credit_topup and settings.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manual credit top-up is disabled",
        )
    await _require_admin(db, user.id, org_id)
    svc = CreditService(db)
    account = await svc.topup(
        org_id,
        body.amount,
        description="manual_topup_dev",
        metadata={"granted_by": str(user.id), "environment": settings.environment},
    )
    return {
        "balance": str(account.balance),
        "reserved": str(account.reserved),
    }


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

    credits_granted = None
    if result.event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        obj = (result.raw.get("data") or {}).get("object") or {}
        meta = obj.get("metadata") or {}
        order_id_str = meta.get("order_id")
        org_id_str = meta.get("organization_id")
        provider_payment_id = result.payment_id or obj.get("id") or event_id

        order = None
        if order_id_str:
            try:
                order = await db.get(Order, uuid.UUID(order_id_str))
            except ValueError:
                order = None

        amount = Decimal("0")
        currency = "USD"
        if order is not None:
            amount = order.amount
            currency = order.currency
            order.status = "paid"
        else:
            try:
                amount_total = obj.get("amount_total")
                if amount_total is not None:
                    amount = (Decimal(int(amount_total)) / Decimal("100")).quantize(Decimal("0.0001"))
                currency = (obj.get("currency") or "usd").upper()
            except Exception:
                pass

        dup = await db.execute(
            select(Payment).where(
                Payment.provider == "stripe",
                Payment.provider_payment_id == str(provider_payment_id),
            )
        )
        if dup.scalar_one_or_none() is None and order is not None:
            pay = Payment(
                id=uuid.uuid4(),
                order_id=order.id,
                provider="stripe",
                provider_payment_id=str(provider_payment_id),
                amount=amount,
                currency=currency,
                status=result.status or "succeeded",
                raw_response=result.raw,
            )
            db.add(pay)

            org_uuid = order.organization_id
            if org_id_str:
                try:
                    org_uuid = uuid.UUID(org_id_str)
                except ValueError:
                    pass
            if amount > 0:
                credit_svc = CreditService(db)
                await credit_svc.topup(
                    org_uuid,
                    amount,
                    description=f"stripe:{provider_payment_id}",
                    metadata={"order_id": str(order.id), "event_id": event_id},
                )
                credits_granted = str(amount)

    await db.flush()
    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": result.event_type,
        "credits_granted": credits_granted,
    }


@router.get("/entitlements/{organization_id}")
async def entitlements(organization_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _require_member(db, user.id, organization_id)
    ent = EntitlementService(db)
    sub = await ent.get_active_subscription(organization_id)
    credits = await ent.available_credits(organization_id)
    return {
        "organization_id": str(organization_id),
        "subscription": {
            "plan_id": sub.plan_id,
            "status": sub.status,
        }
        if sub
        else None,
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

    from app.services.yookassa import YooKassaPaymentProvider, CheckoutRequest as YkReq, Money as YkMoney

    yk = YooKassaPaymentProvider()
    session = await yk.create_checkout(
        YkReq(
            organization_id=str(org_id),
            plan_id=body.plan_id,
            amount=YkMoney(amount=body.amount, currency=order.currency),
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

    event_id = result.payment_id or f"yk_{uuid.uuid4().hex[:16]}"
    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "yookassa",
            WebhookEvent.provider_event_id == event_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": event_id}

    wh = WebhookEvent(
        id=uuid.uuid4(),
        provider="yookassa",
        provider_event_id=event_id,
        event_type=result.event_type,
        payload=result.raw,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(wh)
    await db.flush()
    return {"status": "processed", "event_id": event_id, "event_type": result.event_type}
