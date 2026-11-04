"""Plans, credits, topup, entitlements routes."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.api.billing import (
    TopupRequest,
    _require_admin,
    _require_member,
    router,
)
from app.api.deps import CurrentUser, DbSession
from app.models.billing import TariffPlan
from app.services.credits import CreditService
from app.services.entitlement import EntitlementService


@router.get("/plans")
async def list_plans(db: DbSession):
    from app.services.pricing import BUILTIN_PLANS

    result = await db.execute(select(TariffPlan).where(TariffPlan.is_active.is_(True)))
    plans = result.scalars().all()
    out = [
        {
            "id": p.id,
            "name": p.name,
            "price_monthly": str(p.price_monthly),
            "currency": p.currency,
            "included_credits": str(p.included_credits),
            "features": p.features,
            "source": "db",
        }
        for p in plans
    ]
    if not out:
        out = [
            {
                "id": k,
                "name": v["name"],
                "price_monthly": str(v["price"]),
                "currency": v["currency"],
                "included_credits": str(v["credits"]),
                "features": {"kind": v["kind"]},
                "source": "builtin",
            }
            for k, v in BUILTIN_PLANS.items()
        ]
    return out


@router.get("/credits/{organization_id}")
async def get_credits(organization_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _require_member(db, user.id, organization_id)
    account = await CreditService(db).get_or_create_account(organization_id)
    return {
        "organization_id": str(organization_id),
        "balance": str(account.balance),
        "reserved": str(account.reserved),
        "available": str(account.balance - account.reserved),
    }


@router.post("/credits/topup")
async def topup_credits(body: TopupRequest, user: CurrentUser, db: DbSession):
    from app.core.config import get_settings

    settings = get_settings()
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    if settings.environment == "production" and not settings.allow_manual_credit_topup:
        raise HTTPException(status_code=403, detail="Manual credit top-up is disabled in production")
    if not settings.allow_manual_credit_topup and settings.environment != "development":
        raise HTTPException(status_code=403, detail="Manual credit top-up is disabled")
    await _require_admin(db, user.id, org_id)
    account = await CreditService(db).topup(
        org_id,
        body.amount,
        description="manual_topup_dev",
        metadata={"granted_by": str(user.id), "environment": settings.environment},
    )
    return {"balance": str(account.balance), "reserved": str(account.reserved)}


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
