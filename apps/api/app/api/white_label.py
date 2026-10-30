import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.white_label import WhiteLabelConfig

router = APIRouter(prefix="/white-label", tags=["white-label"])


class WhiteLabelUpsert(BaseModel):
    brand_name: str | None = Field(default=None, max_length=255)
    logo_url: str | None = None
    primary_color: str | None = Field(default=None, max_length=32)
    custom_domain: str | None = Field(default=None, max_length=255)
    config: dict | None = None


class WhiteLabelOut(BaseModel):
    organization_id: str
    brand_name: str | None
    logo_url: str | None
    primary_color: str | None
    custom_domain: str | None
    config: dict | None


async def _require_member(db: DbSession, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    r = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of organization")


@router.get("/{organization_id}", response_model=WhiteLabelOut)
async def get_white_label(organization_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _require_member(db, user.id, organization_id)
    result = await db.execute(
        select(WhiteLabelConfig).where(WhiteLabelConfig.organization_id == organization_id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return WhiteLabelOut(
            organization_id=str(organization_id),
            brand_name=None,
            logo_url=None,
            primary_color=None,
            custom_domain=None,
            config=None,
        )
    return WhiteLabelOut(
        organization_id=str(cfg.organization_id),
        brand_name=cfg.brand_name,
        logo_url=cfg.logo_url,
        primary_color=cfg.primary_color,
        custom_domain=cfg.custom_domain,
        config=cfg.config,
    )


@router.put("/{organization_id}", response_model=WhiteLabelOut)
async def upsert_white_label(
    organization_id: uuid.UUID,
    body: WhiteLabelUpsert,
    user: CurrentUser,
    db: DbSession,
):
    await _require_member(db, user.id, organization_id)
    result = await db.execute(
        select(WhiteLabelConfig).where(WhiteLabelConfig.organization_id == organization_id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = WhiteLabelConfig(id=uuid.uuid4(), organization_id=organization_id)
        db.add(cfg)
    if body.brand_name is not None:
        cfg.brand_name = body.brand_name
    if body.logo_url is not None:
        cfg.logo_url = body.logo_url
    if body.primary_color is not None:
        cfg.primary_color = body.primary_color
    if body.custom_domain is not None:
        cfg.custom_domain = body.custom_domain
    if body.config is not None:
        cfg.config = body.config
    await db.flush()
    return WhiteLabelOut(
        organization_id=str(cfg.organization_id),
        brand_name=cfg.brand_name,
        logo_url=cfg.logo_url,
        primary_color=cfg.primary_color,
        custom_domain=cfg.custom_domain,
        config=cfg.config,
    )


@router.get("/public/by-domain/{domain}", response_model=WhiteLabelOut)
async def public_by_domain(domain: str, db: DbSession):
    result = await db.execute(
        select(WhiteLabelConfig).where(WhiteLabelConfig.custom_domain == domain)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Domain not configured")
    return WhiteLabelOut(
        organization_id=str(cfg.organization_id),
        brand_name=cfg.brand_name,
        logo_url=cfg.logo_url,
        primary_color=cfg.primary_color,
        custom_domain=cfg.custom_domain,
        config=cfg.config,
    )
