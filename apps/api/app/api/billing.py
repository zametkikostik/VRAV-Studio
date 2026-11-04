import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.billing import Order, Payment, TariffPlan, WebhookEvent
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
    plan_id: str
    amount: Decimal | None = None
    currency: str | None = None
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
