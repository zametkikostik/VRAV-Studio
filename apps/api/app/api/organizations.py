"""Organization CRUD and C.2.5 member lifecycle HTTP API."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberOut,
    OrganizationMemberRoleUpdate,
    OrganizationOut,
    OwnershipTransferRequest,
    OwnershipTransferResult,
)
from app.services.rbac import (
    Permission,
    assert_role_assignment_allowed,
    normalize_role,
    require_org_permission,
)
from app.services.security_audit import record_security_audit

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _member_out(m: OrganizationMember) -> OrganizationMemberOut:
    return OrganizationMemberOut(
        id=str(m.id),
        organization_id=str(m.organization_id),
        user_id=str(m.user_id),
        role=normalize_role(m.role),
    )


async def _lock_active_org(db: DbSession, org_id: uuid.UUID) -> Organization:
    """Load organization with FOR UPDATE; deleted/missing → 404."""
    result = await db.execute(
        select(Organization)
        .where(Organization.id == org_id, Organization.deleted_at.is_(None))
        .with_for_update()
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def _assert_owner_invariants(db: DbSession, org: Organization) -> None:
    result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == org.id)
    )
    members = list(result.scalars().all())
    owners = [m for m in members if normalize_role(m.role) == "owner"]
    if len(owners) != 1:
        raise HTTPException(status_code=500, detail="Owner invariant violated")
    if owners[0].user_id != org.owner_user_id:
        raise HTTPException(status_code=500, detail="Owner invariant violated")


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationCreate, user: CurrentUser, db: DbSession):
    slug = body.slug.lower()
    if not re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$", slug) and len(slug) > 1:
        if not re.match(r"^[a-z0-9\-]+$", slug):
            raise HTTPException(status_code=400, detail="Invalid slug")
    existing = await db.execute(select(Organization).where(Organization.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")
    org = Organization(id=uuid.uuid4(), name=body.name, slug=slug, owner_user_id=user.id)
    db.add(org)
    await db.flush()
    db.add(
        OrganizationMember(
            id=uuid.uuid4(), organization_id=org.id, user_id=user.id, role="owner"
        )
    )
    await db.flush()
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan_tier=org.plan_tier,
        owner_user_id=str(org.owner_user_id),
    )


@router.get("", response_model=list[OrganizationOut])
async def list_my_organizations(user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user.id,
            Organization.deleted_at.is_(None),
        )
    )
    return [
        OrganizationOut(
            id=str(o.id),
            name=o.name,
            slug=o.slug,
            plan_tier=o.plan_tier,
            owner_user_id=str(o.owner_user_id),
        )
        for o in result.scalars().all()
    ]


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(org_id: uuid.UUID, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            Organization.id == org_id,
            OrganizationMember.user_id == user.id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan_tier=org.plan_tier,
        owner_user_id=str(org.owner_user_id),
    )


@router.get("/{org_id}/members", response_model=list[OrganizationMemberOut])
async def list_organization_members(org_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _lock_active_org(db, org_id)
    await require_org_permission(db, user.id, org_id, Permission.ORG_MEMBERS_MANAGE)
    result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
    )
    return [_member_out(m) for m in result.scalars().all()]


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_member(
    org_id: uuid.UUID, body: OrganizationMemberCreate, user: CurrentUser, db: DbSession
):
    org = await _lock_active_org(db, org_id)
    actor = await require_org_permission(db, user.id, org_id, Permission.ORG_MEMBERS_MANAGE)
    try:
        target_user_id = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    raw = (body.role or "").lower().strip()
    if raw not in ("admin", "editor", "viewer", "owner"):
        raise HTTPException(status_code=400, detail="Invalid role")
    target_role = normalize_role(body.role)
    if target_role == "owner":
        raise HTTPException(
            status_code=403,
            detail="Cannot assign owner via role update; use ownership transfer",
        )
    assert_role_assignment_allowed(actor.role, target_role)
    ures = await db.execute(
        select(User).where(
            User.id == target_user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if ures.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")
    existing = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Membership already exists")
    member = OrganizationMember(
        id=uuid.uuid4(),
        organization_id=org_id,
        user_id=target_user_id,
        role=target_role,
    )
    db.add(member)
    await db.flush()
    await record_security_audit(
        db,
        event_type="member_added",
        outcome="success",
        actor_user_id=user.id,
        organization_id=org_id,
        target_user_id=target_user_id,
        target_member_id=member.id,
        new_role=target_role,
        details={"target_member_id": str(member.id), "org_slug": org.slug},
    )
    await _assert_owner_invariants(db, org)
    return _member_out(member)


@router.patch("/{org_id}/members/{member_id}", response_model=OrganizationMemberOut)
async def update_organization_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    body: OrganizationMemberRoleUpdate,
    user: CurrentUser,
    db: DbSession,
):
    org = await _lock_active_org(db, org_id)
    actor = await require_org_permission(db, user.id, org_id, Permission.ORG_MEMBERS_MANAGE)
    raw = (body.role or "").lower().strip()
    if raw not in ("admin", "editor", "viewer", "owner"):
        raise HTTPException(status_code=400, detail="Invalid role")
    new_role = normalize_role(body.role)
    if new_role == "owner":
        raise HTTPException(
            status_code=403,
            detail="Cannot assign owner via role update; use ownership transfer",
        )
    mres = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org_id,
        )
    )
    member = mres.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    current = normalize_role(member.role)
    if current == "owner" or member.user_id == org.owner_user_id:
        raise HTTPException(
            status_code=409,
            detail="Cannot change current owner role; use ownership transfer",
        )
    if current == new_role:
        return _member_out(member)
    assert_role_assignment_allowed(actor.role, new_role)
    if normalize_role(actor.role) == "admin" and current == "admin":
        raise HTTPException(status_code=403, detail="Admin cannot modify admin membership")
    previous = current
    member.role = new_role
    await db.flush()
    await record_security_audit(
        db,
        event_type="member_role_changed",
        outcome="success",
        actor_user_id=user.id,
        organization_id=org_id,
        target_user_id=member.user_id,
        target_member_id=member.id,
        previous_role=previous,
        new_role=new_role,
        details={"target_member_id": str(member.id), "org_slug": org.slug},
    )
    await _assert_owner_invariants(db, org)
    return _member_out(member)


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_organization_member(
    org_id: uuid.UUID, member_id: uuid.UUID, user: CurrentUser, db: DbSession
):
    org = await _lock_active_org(db, org_id)
    actor = await require_org_permission(db, user.id, org_id, Permission.ORG_MEMBERS_MANAGE)
    actor_role = normalize_role(actor.role)
    mres = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org_id,
        )
    )
    member = mres.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    target_role = normalize_role(member.role)
    if member.user_id == org.owner_user_id or target_role == "owner":
        raise HTTPException(
            status_code=409,
            detail="Cannot revoke current owner; transfer ownership first",
        )
    if actor_role == "admin" and target_role == "admin" and member.user_id != user.id:
        raise HTTPException(status_code=403, detail="Admin cannot revoke admin or owner")
    if actor_role == "admin" and target_role == "owner":
        raise HTTPException(status_code=403, detail="Admin cannot revoke admin or owner")
    previous = target_role
    target_user_id = member.user_id
    tid = member.id
    await db.delete(member)
    await db.flush()
    await record_security_audit(
        db,
        event_type="member_revoked",
        outcome="success",
        actor_user_id=user.id,
        organization_id=org_id,
        target_user_id=target_user_id,
        target_member_id=tid,
        previous_role=previous,
        details={"target_member_id": str(tid), "org_slug": org.slug},
    )
    await _assert_owner_invariants(db, org)
    return None


@router.post("/{org_id}/transfer-ownership", response_model=OwnershipTransferResult)
async def transfer_organization_ownership(
    org_id: uuid.UUID, body: OwnershipTransferRequest, user: CurrentUser, db: DbSession
):
    org = await _lock_active_org(db, org_id)
    await require_org_permission(db, user.id, org_id, Permission.ORG_TRANSFER_OWNERSHIP)
    try:
        target_user_id = uuid.UUID(body.target_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_user_id")
    if target_user_id == org.owner_user_id:
        raise HTTPException(status_code=409, detail="Target is already the owner")
    cres = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == org.owner_user_id,
        )
    )
    current_owner_mem = cres.scalar_one_or_none()
    if current_owner_mem is None:
        raise HTTPException(status_code=500, detail="Owner membership missing")
    tres = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
    )
    target_mem = tres.scalar_one_or_none()
    if target_mem is None:
        raise HTTPException(status_code=404, detail="Target member not found")
    ures = await db.execute(
        select(User).where(
            User.id == target_user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if ures.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Target user not found")
    previous_owner_user_id = org.owner_user_id
    target_mem.role = "owner"
    org.owner_user_id = target_user_id
    current_owner_mem.role = "admin"
    await db.flush()
    await record_security_audit(
        db,
        event_type="ownership_transferred",
        outcome="success",
        actor_user_id=user.id,
        organization_id=org_id,
        target_user_id=target_user_id,
        target_member_id=target_mem.id,
        previous_role="owner",
        new_role="owner",
        details={
            "previous_owner_user_id": str(previous_owner_user_id),
            "new_owner_user_id": str(target_user_id),
            "org_slug": org.slug,
        },
    )
    await _assert_owner_invariants(db, org)
    return OwnershipTransferResult(
        organization_id=str(org_id),
        previous_owner_user_id=str(previous_owner_user_id),
        new_owner_user_id=str(target_user_id),
        previous_owner_new_role="admin",
    )


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(org_id: uuid.UUID, user: CurrentUser, db: DbSession):
    org = await _lock_active_org(db, org_id)
    await require_org_permission(db, user.id, org_id, Permission.ORG_DELETE)
    await _assert_owner_invariants(db, org)
    org.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await record_security_audit(
        db,
        event_type="organization_deleted",
        outcome="success",
        actor_user_id=user.id,
        organization_id=org_id,
        details={"org_slug": org.slug, "reason_code": "owner_soft_delete"},
    )
    return None
