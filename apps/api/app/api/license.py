"""License issuance — paid order or explicit admin flag only."""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.billing import Order, Payment
from app.models.organization import OrganizationMember
from app.services.license import LicenseService
from app.services.license_policy import allow_admin_license_issue, resolve_plan_caps

router = APIRouter(prefix="/licenses", tags=["licenses"])


async def _require_org_admin(db: DbSession, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    row = mem.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=403, detail="Not a member of organization")
    if row.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")


class IssueLicenseRequest(BaseModel):
    organization_id: str
    order_id: str | None = None
    plan_id: str = "selfhosted"
    max_installations: int | None = Field(default=None, ge=1, le=1000)
    valid_until: datetime | None = None
    features: dict | None = None


class LicenseOut(BaseModel):
    id: str
    license_key: str
    organization_id: str | None
    plan_id: str | None
    max_installations: int
    status: str
    valid_until: datetime | None
    features: dict | None


class VerifyRequest(BaseModel):
    license_key: str
    installation_id: str = Field(min_length=1, max_length=128)
    machine_fingerprint: str | None = None
    bind: bool = True


class DeactivateRequest(BaseModel):
    license_key: str
    installation_id: str


def _allow_admin_issue() -> bool:
    return allow_admin_license_issue()


@router.post("/issue", response_model=LicenseOut, status_code=status.HTTP_201_CREATED)
async def issue_license(body: IssueLicenseRequest, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_org_admin(db, user.id, org_id)

    plan_id, max_inst, features = resolve_plan_caps(body.plan_id)

    authorized = False
    if body.order_id:
        try:
            order_uuid = uuid.UUID(body.order_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid order_id")
        order = await db.get(Order, order_uuid)
        if order is None or order.organization_id != org_id:
            raise HTTPException(status_code=403, detail="Order not found for organization")
        if order.status != "paid":
            raise HTTPException(status_code=402, detail="Order is not paid")
        pay = await db.execute(
            select(Payment).where(Payment.order_id == order.id, Payment.status == "succeeded")
        )
        if pay.scalar_one_or_none() is None:
            raise HTTPException(status_code=402, detail="No succeeded payment for order")
        authorized = True
    elif _allow_admin_issue():
        authorized = True

    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="License issue requires paid order_id (or ALLOW_ADMIN_LICENSE_ISSUE)",
        )

    svc = LicenseService(db)
    try:
        lic = await svc.issue(
            organization_id=org_id,
            plan_id=plan_id,
            max_installations=max_inst,
            valid_until=body.valid_until,
            features=features,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return LicenseOut(
        id=str(lic.id),
        license_key=lic.license_key,
        organization_id=str(lic.organization_id) if lic.organization_id else None,
        plan_id=lic.plan_id,
        max_installations=lic.max_installations,
        status=lic.status,
        valid_until=lic.valid_until,
        features=lic.features,
    )


@router.post("/verify")
async def verify_license(body: VerifyRequest, db: DbSession):
    svc = LicenseService(db)
    result = await svc.verify(
        body.license_key, body.installation_id, body.machine_fingerprint, bind=body.bind
    )
    return result.model_dump(mode="json")


@router.post("/deactivate")
async def deactivate_installation(body: DeactivateRequest, db: DbSession):
    svc = LicenseService(db)
    ok = await svc.deactivate_installation(body.license_key, body.installation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Installation not found")
    return {"ok": True}


@router.post("/{license_key}/revoke")
async def revoke_license(license_key: str, user: CurrentUser, db: DbSession):
    from app.models.license import License

    result = await db.execute(select(License).where(License.license_key == license_key))
    existing = result.scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="License not found")
    if existing.organization_id is not None:
        await _require_org_admin(db, user.id, existing.organization_id)
    else:
        raise HTTPException(status_code=403, detail="Cannot revoke unscoped license")
    lic = await LicenseService(db).revoke(license_key)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found")
    return {"license_key": license_key, "status": lic.status}


class OfflineTokenRequest(BaseModel):
    license_key: str
    installation_id: str
    machine_fingerprint: str | None = None


@router.post("/offline-token")
async def issue_offline_token_endpoint(body: OfflineTokenRequest, db: DbSession):
    from app.services.license_token import issue_offline_token

    svc = LicenseService(db)
    status_result = await svc.verify(
        body.license_key, body.installation_id, body.machine_fingerprint, bind=True
    )
    if not status_result.valid:
        raise HTTPException(status_code=403, detail=status_result.model_dump(mode="json"))
    token = issue_offline_token(
        license_key=body.license_key,
        license_id=status_result.license_id or "",
        max_installations=status_result.max_installations or 1,
        features=status_result.features,
        valid_until=status_result.valid_until,
        ttl_days=14,
    )
    return {"offline_token": token, "license": status_result.model_dump(mode="json")}


@router.post("/offline-token/verify")
async def verify_offline_token_endpoint(body: dict):
    from app.services.license_token import verify_offline_token

    token = body.get("token") or body.get("offline_token")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    payload = verify_offline_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return {"valid": True, "claims": payload}
