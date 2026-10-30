import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.ai_connection import UserAIConnection
from app.models.organization import OrganizationMember
from app.services.crypto import encrypt_secret, key_hint

router = APIRouter(prefix="/ai/connections", tags=["ai-connections"])

ALLOWED_PROVIDERS = {"xai", "openrouter", "routerai", "mock"}


class ConnectionCreate(BaseModel):
    organization_id: str
    provider_id: str = Field(pattern=r"^[a-z0-9_]+$")
    api_key: str = Field(min_length=8, max_length=512)


class ConnectionOut(BaseModel):
    id: str
    organization_id: str
    provider_id: str
    key_hint: str | None
    is_active: bool


async def _require_member(db, user_id, org_id):
    r = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(body: ConnectionCreate, user: CurrentUser, db: DbSession):
    if body.provider_id not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {sorted(ALLOWED_PROVIDERS)}")
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_member(db, user.id, org_id)

    existing = await db.execute(
        select(UserAIConnection).where(
            UserAIConnection.organization_id == org_id,
            UserAIConnection.provider_id == body.provider_id,
            UserAIConnection.user_id == user.id,
        )
    )
    for row in existing.scalars().all():
        row.is_active = False

    conn = UserAIConnection(
        id=uuid.uuid4(),
        user_id=user.id,
        organization_id=org_id,
        provider_id=body.provider_id,
        encrypted_api_key=encrypt_secret(body.api_key),
        key_hint=key_hint(body.api_key),
        is_active=True,
    )
    db.add(conn)
    await db.flush()
    return ConnectionOut(
        id=str(conn.id),
        organization_id=str(conn.organization_id),
        provider_id=conn.provider_id,
        key_hint=conn.key_hint,
        is_active=conn.is_active,
    )


@router.get("", response_model=list[ConnectionOut])
async def list_connections(organization_id: str, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    await _require_member(db, user.id, org_id)
    result = await db.execute(
        select(UserAIConnection).where(
            UserAIConnection.organization_id == org_id,
            UserAIConnection.user_id == user.id,
            UserAIConnection.is_active.is_(True),
        )
    )
    return [
        ConnectionOut(
            id=str(c.id),
            organization_id=str(c.organization_id),
            provider_id=c.provider_id,
            key_hint=c.key_hint,
            is_active=c.is_active,
        )
        for c in result.scalars().all()
    ]


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(connection_id: uuid.UUID, user: CurrentUser, db: DbSession):
    conn = await db.get(UserAIConnection, connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    conn.is_active = False
    await db.flush()
