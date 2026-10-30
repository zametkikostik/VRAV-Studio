import re
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import Organization, OrganizationMember
from app.schemas.organization import OrganizationCreate, OrganizationOut

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationCreate, user: CurrentUser, db: DbSession):
    slug = body.slug.lower()
    if not re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$", slug) and len(slug) > 1:
        if not re.match(r"^[a-z0-9\-]+$", slug):
            raise HTTPException(status_code=400, detail="Invalid slug")
    existing = await db.execute(select(Organization).where(Organization.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")
    org = Organization(
        id=uuid.uuid4(),
        name=body.name,
        slug=slug,
        owner_user_id=user.id,
    )
    db.add(org)
    await db.flush()
    member = OrganizationMember(
        id=uuid.uuid4(),
        organization_id=org.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)
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
    orgs = result.scalars().all()
    return [
        OrganizationOut(
            id=str(o.id),
            name=o.name,
            slug=o.slug,
            plan_tier=o.plan_tier,
            owner_user_id=str(o.owner_user_id),
        )
        for o in orgs
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
