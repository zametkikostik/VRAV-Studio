"""Extra Postgres billing cases for Iteration 10 (skipped without DATABASE_URL)."""
from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal

import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "")
REQUIRES_PG = not DATABASE_URL.startswith("postgresql")

pytestmark = pytest.mark.skipif(
    REQUIRES_PG,
    reason="DATABASE_URL must be postgresql+asyncpg://... for billing integration tests",
)


async def _session_factory():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    return engine, Session


async def _seed(session, *, credits="100.0000", amount="10.0000"):
    from app.models.user import User
    from app.models.organization import Organization, OrganizationMember
    from app.models.billing import Order
    from app.core.security import hash_password

    uid = uuid.uuid4()
    oid = uuid.uuid4()
    order_id = uuid.uuid4()
    session.add(
        User(
            id=uid,
            email=f"i10_{uid.hex[:10]}@example.com",
            password_hash=hash_password("TestPass123!"),
            is_active=True,
        )
    )
    await session.flush()
    session.add(Organization(id=oid, name="I10", slug=f"i10-{uid.hex[:8]}", owner_user_id=uid))
    await session.flush()
    session.add(OrganizationMember(organization_id=oid, user_id=uid, role="owner"))
    session.add(
        Order(
            id=order_id,
            organization_id=oid,
            amount=Decimal(amount),
            currency="USD",
            status="pending",
            plan_id="credits_100",
            credits_to_grant=Decimal(credits),
            pricing_kind="credits",
            provider="stripe",
            snapshot={"amount": amount, "currency": "USD", "credits_to_grant": credits},
        )
    )
    await session.flush()
    return oid, order_id


def test_pg_payment_id_cannot_attach_two_orders():
    async def _run():
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update

        engine, Session = await _session_factory()
        async with Session() as session:
            _, order_a = await _seed(session)
            _, order_b = await _seed(session)
            pay_id = f"pi_shared_{order_a.hex[:10]}"
            oa = await load_order_for_update(session, order_a)
            r1, _ = await grant_paid_order_credits(
                session, order=oa, provider="stripe", provider_payment_id=pay_id,
                event_id="evt_a", raw_response={},
            )
            assert r1 == "granted"
            ob = await load_order_for_update(session, order_b)
            r2, g2 = await grant_paid_order_credits(
                session, order=ob, provider="stripe", provider_payment_id=pay_id,
                event_id="evt_b", raw_response={},
            )
            assert r2 == "payment_already_recorded"
            assert g2 is None
            assert ob.status == "pending"
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())


def test_pg_license_zero_credits_allowed_with_positive_amount():
    async def _run():
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update

        engine, Session = await _session_factory()
        async with Session() as session:
            _, order_id = await _seed(session, amount="199.0000", credits="0.0000")
            order = await load_order_for_update(session, order_id)
            reason, granted = await grant_paid_order_credits(
                session, order=order, provider="stripe",
                provider_payment_id=f"pi_lic_{order_id.hex[:8]}",
                event_id="evt_lic", raw_response={},
            )
            assert reason == "granted"
            assert granted is None
            assert order.status == "paid"
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())
