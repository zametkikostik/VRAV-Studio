"""Allowlisted durable security audit writer.

Records are staged on the caller's AsyncSession and must be committed
together with the corresponding privileged mutation (same transaction).
This helper never commits and never schedules background work.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_audit import SecurityAuditEvent

EVENT_TYPES = frozenset(
    {
        "member_added",
        "member_role_changed",
        "member_revoked",
        "ownership_transferred",
        "organization_deleted",
    }
)

OUTCOMES = frozenset({"success", "denied", "error"})

DETAILS_ALLOWLIST = frozenset(
    {
        "target_member_id",
        "previous_owner_user_id",
        "new_owner_user_id",
        "reason_code",
        "org_slug",
    }
)


def _sanitize_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if key not in DETAILS_ALLOWLIST:
            continue
        if value is None:
            continue
        if isinstance(value, uuid.UUID):
            cleaned[key] = str(value)
        elif isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned or None


async def record_security_audit(
    session: AsyncSession,
    *,
    event_type: str,
    outcome: str,
    actor_user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    target_member_id: uuid.UUID | None = None,
    previous_role: str | None = None,
    new_role: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityAuditEvent:
    """Stage a durable audit row on ``session`` (no commit).

    Raises ValueError if event_type or outcome is not allowlisted.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type not allowlisted: {event_type}")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome not allowlisted: {outcome}")

    event = SecurityAuditEvent(
        id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        target_user_id=target_user_id,
        target_member_id=target_member_id,
        event_type=event_type,
        outcome=outcome,
        previous_role=previous_role,
        new_role=new_role,
        request_id=(request_id[:64] if request_id else None),
        details=_sanitize_details(details),
    )
    session.add(event)
    return event
