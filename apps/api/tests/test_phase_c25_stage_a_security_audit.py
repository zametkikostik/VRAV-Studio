"""Phase C.2.5 Stage A — dedicated security_audit regression (PostgreSQL 16).

Covers allowlists, details sanitization, no independent commit, and durable insert.
Missing DATABASE_URL fails closed (never skipped).
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required for Stage A security_audit tests "
        "(PostgreSQL 16). Refusing to skip or pass without infrastructure."
    )

from app.models.security_audit import SecurityAuditEvent
from app.services.security_audit import (
    DETAILS_ALLOWLIST,
    EVENT_TYPES,
    OUTCOMES,
    _sanitize_details,
    record_security_audit,
)


@pytest.mark.asyncio
async def test_invalid_event_type_raises_value_error():
    session = MagicMock(spec=AsyncSession)
    session.add = MagicMock()
    with pytest.raises(ValueError, match="event_type not allowlisted"):
        await record_security_audit(
            session,
            event_type="not_a_real_event",
            outcome="success",
        )
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_outcome_raises_value_error():
    session = MagicMock(spec=AsyncSession)
    session.add = MagicMock()
    # pick a valid event_type so only outcome fails
    valid_event = next(iter(EVENT_TYPES))
    with pytest.raises(ValueError, match="outcome not allowlisted"):
        await record_security_audit(
            session,
            event_type=valid_event,
            outcome="not_a_real_outcome",
        )
    session.add.assert_not_called()


def test_sanitize_details_allowlist_and_scalars():
    tid = uuid.uuid4()
    raw = {
        "org_slug": "acme",
        "reason_code": "owner_soft_delete",
        "target_member_id": tid,
        "password": "secret",
        "token": "x",
        "nested": {"a": 1},
        "previous_owner_user_id": str(uuid.uuid4()),
        "new_owner_user_id": uuid.uuid4(),
        "ignored_none": None,
    }
    cleaned = _sanitize_details(raw)
    assert cleaned is not None
    assert "password" not in cleaned
    assert "token" not in cleaned
    assert "nested" not in cleaned or cleaned.get("nested") == str({"a": 1})
    # nested is not scalar str/int/float/bool/UUID — implementation coerces via str()
    # only allowlisted keys survive
    for key in cleaned:
        assert key in DETAILS_ALLOWLIST
    assert cleaned["org_slug"] == "acme"
    assert cleaned["reason_code"] == "owner_soft_delete"
    assert cleaned["target_member_id"] == str(tid)
    assert isinstance(cleaned["new_owner_user_id"], str)
    assert "ignored_none" not in cleaned
    assert _sanitize_details(None) is None
    assert _sanitize_details({}) is None


@pytest.mark.asyncio
async def test_record_security_audit_stages_without_commit():
    """Helper must session.add the event and must not call session.commit."""
    session = MagicMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()

    event = await record_security_audit(
        session,
        event_type="member_added",
        outcome="success",
        actor_user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        details={"org_slug": "life-a", "password": "nope"},
    )
    assert isinstance(event, SecurityAuditEvent)
    assert event.event_type == "member_added"
    assert event.outcome == "success"
    assert event.details is not None
    assert "password" not in event.details
    assert event.details.get("org_slug") == "life-a"
    session.add.assert_called_once_with(event)
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_postgres_insert_and_read_back_success_event():
    """Durable insert of a success audit row and read-back on real PostgreSQL."""
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    event_id = None
    try:
        async with Session() as session, session.begin():
            # Nullable FKs: insert without requiring seed users/orgs.
            ev = await record_security_audit(
                session,
                event_type="organization_deleted",
                outcome="success",
                actor_user_id=None,
                organization_id=None,
                details={"org_slug": "stage-a-probe", "reason_code": "owner_soft_delete"},
            )
            event_id = ev.id
        # after commit of begin block, row must be durable
        async with Session() as session:
            row = await session.get(SecurityAuditEvent, event_id)
            assert row is not None
            assert row.event_type == "organization_deleted"
            assert row.outcome == "success"
            assert row.details is not None
            assert row.details.get("org_slug") == "stage-a-probe"
            assert row.details.get("reason_code") == "owner_soft_delete"
            async with session.begin():
                await session.delete(row)
    finally:
        await engine.dispose()


def test_allowlists_are_non_empty_and_match_production_contract():
    assert "member_added" in EVENT_TYPES
    assert "ownership_transferred" in EVENT_TYPES
    assert "success" in OUTCOMES
    assert "denied" in OUTCOMES
    assert "org_slug" in DETAILS_ALLOWLIST
