"""GDPR data export and deletion."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIUsageEvent
from app.models.ai_connection import UserAIConnection
from app.models.organization import OrganizationMember
from app.models.user import User


async def export_user_data(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("user not found")

    memberships = (
        await db.execute(select(OrganizationMember).where(OrganizationMember.user_id == user_id))
    ).scalars().all()

    usage = (
        await db.execute(
            select(AIUsageEvent)
            .where(AIUsageEvent.user_id == user_id)
            .order_by(AIUsageEvent.created_at.desc())
            .limit(5000)
        )
    ).scalars().all()

    connections = (
        await db.execute(select(UserAIConnection).where(UserAIConnection.user_id == user_id))
    ).scalars().all()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "is_active": user.is_active,
        },
        "memberships": [
            {"organization_id": str(m.organization_id), "role": m.role} for m in memberships
        ],
        "ai_connections": [
            {
                "id": str(c.id),
                "provider_id": c.provider_id,
                "key_hint": c.key_hint,
                "is_active": c.is_active,
            }
            for c in connections
        ],
        "ai_usage_events_sample": [
            {
                "id": str(e.id),
                "provider_id": e.provider_id,
                "model_id": e.model_id,
                "total_tokens": e.total_tokens,
                "cost_credits": str(e.cost_credits),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in usage
        ],
    }


async def anonymize_user(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("user not found")

    now = datetime.now(timezone.utc)
    user.email = f"deleted+{user.id}@anonymized.local"
    user.full_name = None
    user.password_hash = None
    user.is_active = False
    user.deleted_at = now

    result = await db.execute(select(UserAIConnection).where(UserAIConnection.user_id == user_id))
    for conn in result.scalars().all():
        conn.is_active = False
        conn.encrypted_api_key = b""
        conn.key_hint = None

    await db.flush()
    return {"user_id": str(user_id), "anonymized_at": now.isoformat()}


async def purge_soft_deleted(db: AsyncSession, retention_days: int = 30) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        select(User).where(User.deleted_at.is_not(None), User.deleted_at < cutoff)
    )
    users = result.scalars().all()
    count = 0
    for u in users:
        mems = (
            await db.execute(select(OrganizationMember).where(OrganizationMember.user_id == u.id))
        ).scalars().all()
        for m in mems:
            await db.delete(m)
        await db.delete(u)
        count += 1
    await db.flush()
    return count
