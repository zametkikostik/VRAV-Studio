"""Stale credit reservation cleanup (imported/called from CreditService)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.billing import CreditReservation


async def release_stale_reservations(credit_service, older_than_seconds: int = 3600) -> int:
    """Release pending reservations older than TTL. Idempotent per row."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    result = await credit_service.db.execute(
        select(CreditReservation).where(
            CreditReservation.status == "pending",
            CreditReservation.created_at < cutoff,
        )
    )
    rows = list(result.scalars().all())
    n = 0
    for res in rows:
        try:
            await credit_service.release(res.id)
            n += 1
        except Exception:
            continue
    return n
