"""Credit ledger list routes (split to keep billing.py size manageable)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.billing import CreditLedger
from app.models.organization import OrganizationMember
from app.services.credits import CreditService

router = APIRouter(prefix="/billing", tags=["billing"])


async def _require_member(db: DbSession, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    from fastapi import HTTPException

    r = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of organization")


@router.get("/ledger/{organization_id}")
async def list_ledger(
    organization_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    limit: int = 50,
):
    """Recent immutable credit ledger entries for the organization."""
    await _require_member(db, user.id, organization_id)
    account = await CreditService(db).get_or_create_account(organization_id)
    lim = max(1, min(limit, 200))
    result = await db.execute(
        select(CreditLedger)
        .where(CreditLedger.account_id == account.id)
        .order_by(CreditLedger.id.desc())
        .limit(lim)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "type": e.entry_type,
            "amount": str(e.amount),
            "balance_after": str(e.balance_after),
            "description": e.description or "",
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]
