"""PostgreSQL behavioral tests for billing integrity (Iter9).

Skipped unless DATABASE_URL points at PostgreSQL (CI e2e / local docker).
"""
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


async def _seed_org_order(session, *, credits: str = "100.0000", amount: str = "10.0000"):
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
            email=f"iter9_{uid.hex[:10]}@example.com",
            password_hash=hash_password("TestPass123!"),
            full_name="Iter9",
            is_active=True,
        )
    )
    await session.flush()
    session.add(
        Organization(id=oid, name="Iter9 Org", slug=f"iter9-{uid.hex[:8]}", owner_user_id=uid)
    )
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
            snapshot={
                "plan_id": "credits_100",
                "amount": amount,
                "currency": "USD",
                "credits_to_grant": credits,
                "provider": "stripe",
            },
        )
    )
    await session.flush()
    return uid, oid, order_id


def test_pg_grant_once_then_order_already_paid():
    async def _run():
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update
        from app.models.billing import Payment, CreditLedger, CreditAccount
        from sqlalchemy import select, func

        engine, Session = await _session_factory()
        async with Session() as session:
            _, oid, order_id = await _seed_org_order(session)
            order = await load_order_for_update(session, order_id)
            r1, g1 = await grant_paid_order_credits(
                session,
                order=order,
                provider="stripe",
                provider_payment_id=f"pi_{order_id.hex[:16]}",
                event_id=f"evt_{order_id.hex[:12]}",
                raw_response={"ok": True},
            )
            assert r1 == "granted"
            assert g1 == "100.0000"

            order2 = await load_order_for_update(session, order_id)
            r2, g2 = await grant_paid_order_credits(
                session,
                order=order2,
                provider="stripe",
                provider_payment_id=f"pi_other_{order_id.hex[:12]}",
                event_id=f"evt_other_{order_id.hex[:8]}",
                raw_response={},
            )
            assert r2 == "order_already_paid"
            assert g2 is None

            pays = (
                await session.execute(
                    select(func.count()).select_from(Payment).where(
                        Payment.order_id == order_id, Payment.status == "succeeded"
                    )
                )
            ).scalar_one()
            assert pays == 1

            bal = (
                await session.execute(
                    select(CreditAccount).where(CreditAccount.organization_id == oid)
                )
            ).scalar_one()
            assert bal.balance == Decimal("100.0000")

            ledger_n = (
                await session.execute(
                    select(func.count())
                    .select_from(CreditLedger)
                    .where(CreditLedger.account_id == bal.id)
                )
            ).scalar_one()
            assert ledger_n >= 1
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())


def test_pg_concurrent_grants_single_success():
    async def _run():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update
        from app.models.billing import Payment
        from sqlalchemy import select, func
        from sqlalchemy.exc import IntegrityError

        engine, Session = await _session_factory()
        async with Session() as session:
            _, _, order_id = await _seed_org_order(session)
            await session.commit()

        engine2 = create_async_engine(DATABASE_URL, pool_size=5, pool_pre_ping=True)
        Session2 = async_sessionmaker(
            engine2, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

        async def attempt(payment_suffix: str):
            async with Session2() as s:
                try:
                    order = await load_order_for_update(s, order_id)
                    reason, granted = await grant_paid_order_credits(
                        s,
                        order=order,
                        provider="stripe",
                        provider_payment_id=f"pi_conc_{payment_suffix}_{order_id.hex[:8]}",
                        event_id=f"evt_conc_{payment_suffix}",
                        raw_response={},
                    )
                    await s.commit()
                    return reason, granted
                except IntegrityError:
                    await s.rollback()
                    return "integrity", None
                except Exception as e:
                    await s.rollback()
                    return f"error:{type(e).__name__}", None

        results = await asyncio.gather(attempt("a"), attempt("b"))
        reasons = [r[0] for r in results]
        assert reasons.count("granted") == 1, results

        async with Session2() as s:
            n = (
                await s.execute(
                    select(func.count()).select_from(Payment).where(
                        Payment.order_id == order_id, Payment.status == "succeeded"
                    )
                )
            ).scalar_one()
            assert n == 1
            await s.rollback()
        await engine.dispose()
        await engine2.dispose()

    asyncio.run(_run())


def test_pg_yookassa_pending_then_succeeded_notification_keys():
    async def _run():
        from app.models.billing import WebhookEvent, CreditAccount
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update
        from sqlalchemy import select

        engine, Session = await _session_factory()
        async with Session() as session:
            _, oid, order_id = await _seed_org_order(session, amount="10.0000", credits="50.0000")
            payment_id = f"yk_{order_id.hex[:16]}"

            session.add(
                WebhookEvent(
                    id=uuid.uuid4(),
                    provider="yookassa",
                    provider_event_id=f"{payment_id}:payment.waiting_for_capture",
                    event_type="payment.waiting_for_capture",
                    payload={"status": "pending"},
                )
            )
            await session.flush()
            session.add(
                WebhookEvent(
                    id=uuid.uuid4(),
                    provider="yookassa",
                    provider_event_id=f"{payment_id}:payment.succeeded",
                    event_type="payment.succeeded",
                    payload={"status": "succeeded"},
                )
            )
            await session.flush()

            order = await load_order_for_update(session, order_id)
            reason, granted = await grant_paid_order_credits(
                session,
                order=order,
                provider="yookassa",
                provider_payment_id=payment_id,
                event_id=f"{payment_id}:payment.succeeded",
                raw_response={},
            )
            assert reason == "granted"
            assert granted == "50.0000"

            order2 = await load_order_for_update(session, order_id)
            r2, _ = await grant_paid_order_credits(
                session,
                order=order2,
                provider="yookassa",
                provider_payment_id=payment_id,
                event_id=f"{payment_id}:payment.succeeded",
                raw_response={},
            )
            assert r2 in ("order_already_paid", "payment_already_recorded")

            bal = (
                await session.execute(
                    select(CreditAccount).where(CreditAccount.organization_id == oid)
                )
            ).scalar_one()
            assert bal.balance == Decimal("50.0000")
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())


def test_pg_invalid_amount_does_not_mark_paid():
    async def _run():
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update

        engine, Session = await _session_factory()
        async with Session() as session:
            _, _, order_id = await _seed_org_order(session, amount="0.0000", credits="10.0000")
            order = await load_order_for_update(session, order_id)
            reason, granted = await grant_paid_order_credits(
                session,
                order=order,
                provider="stripe",
                provider_payment_id="pi_zero",
                event_id="evt_zero",
                raw_response={},
            )
            assert reason == "invalid_amount"
            assert granted is None
            assert order.status == "pending"
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())


def test_pg_missing_snapshot_no_grant():
    async def _run():
        from app.models.user import User
        from app.models.organization import Organization, OrganizationMember
        from app.models.billing import Order
        from app.services.billing_grant import grant_paid_order_credits, load_order_for_update
        from app.core.security import hash_password

        engine, Session = await _session_factory()
        async with Session() as session:
            uid = uuid.uuid4()
            oid = uuid.uuid4()
            order_id = uuid.uuid4()
            session.add(
                User(
                    id=uid,
                    email=f"legacy_{uid.hex[:8]}@ex.com",
                    password_hash=hash_password("x"),
                    is_active=True,
                )
            )
            await session.flush()
            session.add(
                Organization(id=oid, name="L", slug=f"leg-{uid.hex[:6]}", owner_user_id=uid)
            )
            await session.flush()
            session.add(OrganizationMember(organization_id=oid, user_id=uid, role="owner"))
            session.add(
                Order(
                    id=order_id,
                    organization_id=oid,
                    amount=Decimal("10"),
                    currency="USD",
                    status="pending",
                    credits_to_grant=None,
                )
            )
            await session.flush()
            order = await load_order_for_update(session, order_id)
            reason, granted = await grant_paid_order_credits(
                session,
                order=order,
                provider="stripe",
                provider_payment_id="pi_legacy",
                event_id="evt_legacy",
                raw_response={},
            )
            assert reason == "missing_snapshot"
            assert granted is None
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())
