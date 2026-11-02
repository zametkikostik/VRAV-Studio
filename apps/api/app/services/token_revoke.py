"""JWT revocation helpers (revoked_jtis table)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_token import RevokedJti


async def revoke_jti(
    db: AsyncSession,
    jti: str,
    *,
    expires_at: datetime,
    user_id: uuid.UUID | None = None,
) -> None:
    if not jti:
        return
    existing = await db.get(RevokedJti, jti)
    if existing is not None:
        return
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    db.add(RevokedJti(jti=jti, user_id=user_id, expires_at=exp))
    await db.flush()


async def is_jti_revoked(db: AsyncSession, jti: str | None) -> bool:
    if not jti:
        return False
    row = await db.get(RevokedJti, jti)
    if row is None:
        return False
    now = datetime.now(timezone.utc)
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        return False
    return True
