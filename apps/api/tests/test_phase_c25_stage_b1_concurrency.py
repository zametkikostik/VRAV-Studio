"""Phase C.2.5 Stage B.1 — PostgreSQL concurrency for org membership lifecycle.

Frozen design: C1A, C2a, C2b, C4, exact audit cardinality, transfer audit rollback.
Real FastAPI ASGI + real PostgreSQL. No mocked RBAC.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required for Stage B.1 concurrency tests "
        "(PostgreSQL 16). Refusing to skip or pass without infrastructure."
    )

# Longer than bounded lock-wait poll so intentional holds are not cancelled.
_HTTP_TIMEOUT = 30.0
_LOCK_WAIT_TIMEOUT = 8.0


def _auth(uid: uuid.UUID) -> dict:
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(str(uid), token_version=0)}"}


@asynccontextmanager
async def _http_harness():
    from app.db.session import get_db
    from app.main import create_app

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=_HTTP_TIMEOUT,
    )
    try:
        yield Session, client, app
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        await engine.dispose()


async def _seed(Session) -> dict:
    from app.core.security import hash_password
    from app.models.organization import Organization, OrganizationMember
    from app.models.user import User

    owner, target, outsider = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_id = uuid.uuid4()
    member_ids: dict[str, uuid.UUID] = {}
    async with Session() as s, s.begin():
        for uid, email in [
            (owner, f"b1o_{owner.hex[:8]}@ex.com"),
            (target, f"b1t_{target.hex[:8]}@ex.com"),
            (outsider, f"b1u_{outsider.hex[:8]}@ex.com"),
        ]:
            s.add(
                User(
                    id=uid,
                    email=email,
                    password_hash=hash_password("x"),
                    is_active=True,
                )
            )
        await s.flush()
        s.add(
            Organization(
                id=org_id,
                name="B1 Org",
                slug=f"b1-{org_id.hex[:10]}",
                owner_user_id=owner,
            )
        )
        await s.flush()
        for uid, role, key in [
            (owner, "owner", "owner"),
            (target, "editor", "target"),
        ]:
            mid = uuid.uuid4()
            s.add(
                OrganizationMember(
                    id=mid, organization_id=org_id, user_id=uid, role=role
                )
            )
            member_ids[key] = mid
    return {
        "owner": owner,
        "target": target,
        "outsider": outsider,
        "org_id": org_id,
        "member_ids": member_ids,
    }


async def _audit_success_count(Session, org_id: uuid.UUID, event_type: str) -> int:
    from app.models.security_audit import SecurityAuditEvent

    async with Session() as s:
        r = await s.execute(
            select(SecurityAuditEvent).where(
                SecurityAuditEvent.organization_id == org_id,
                SecurityAuditEvent.event_type == event_type,
                SecurityAuditEvent.outcome == "success",
            )
        )
        return len(list(r.scalars().all()))


async def _org_state(Session, org_id: uuid.UUID) -> dict:
    from app.models.organization import Organization, OrganizationMember

    async with Session() as s:
        org = await s.get(Organization, org_id)
        res = await s.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id
            )
        )
        members = list(res.scalars().all())
        owners = [m for m in members if m.role == "owner"]
        by_user = {m.user_id: m.role for m in members}
        return {
            "owner_user_id": org.owner_user_id if org else None,
            "owners": owners,
            "by_user": by_user,
            "member_count": len(members),
        }


async def _wait_blocked_by(
    Session, waiter_pid: int, blocker_pid: int, timeout_s: float = _LOCK_WAIT_TIMEOUT
) -> bool:
    """Poll until waiter_pid is blocked by blocker_pid via pg_blocking_pids."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        async with Session() as s:
            row = (
                await s.execute(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": waiter_pid}
                )
            ).scalar()
            blockers = list(row) if row is not None else []
            if blocker_pid in blockers:
                return True
        await asyncio.sleep(0.05)
    return False


class _LockHoldController:
    """Test-only coordination for first-holder / second-waiter org row locks."""

    def __init__(self) -> None:
        self.lock_held = asyncio.Event()
        self.second_lock_attempting = asyncio.Event()
        self.release_gate = asyncio.Event()
        self.first_pid: int | None = None
        self.second_pid: int | None = None
        self._order = 0
        self._order_lock = asyncio.Lock()

    def install(self, monkeypatch, org_api, real_lock) -> None:
        ctrl = self

        async def instrumented_lock(db, oid):
            # Capture backend PID on this request session BEFORE FOR UPDATE.
            pid = int((await db.execute(text("SELECT pg_backend_pid()"))).scalar())
            async with ctrl._order_lock:
                ctrl._order += 1
                n = ctrl._order
            if n == 1:
                ctrl.first_pid = pid
                org = await real_lock(db, oid)
                ctrl.lock_held.set()
                await ctrl.release_gate.wait()
                return org
            ctrl.second_pid = pid
            ctrl.second_lock_attempting.set()
            # Blocks here on org FOR UPDATE while request 1 holds the row.
            return await real_lock(db, oid)

        monkeypatch.setattr(org_api, "_lock_active_org", instrumented_lock)

    async def wait_second_blocked(self, Session) -> None:
        await asyncio.wait_for(self.lock_held.wait(), timeout=5.0)
        await asyncio.wait_for(self.second_lock_attempting.wait(), timeout=5.0)
        assert self.first_pid is not None
        assert self.second_pid is not None
        ok = await _wait_blocked_by(Session, self.second_pid, self.first_pid)
        assert ok, (
            f"expected second HTTP backend pid {self.second_pid} blocked by "
            f"first pid {self.first_pid} (pg_blocking_pids)"
        )


@pytest.mark.asyncio
async def test_c1a_same_owner_concurrent_transfer_second_gets_403(monkeypatch):
    """C1A: two transfers from same original owner O → {200, 403}; one owner T."""
    from app.api import organizations as org_api

    async with _http_harness() as (Session, client, _app):
        ctx = await _seed(Session)
        org_id = ctx["org_id"]
        o, t = ctx["owner"], ctx["target"]

        ctrl = _LockHoldController()
        ctrl.install(monkeypatch, org_api, org_api._lock_active_org)

        async def do_transfer():
            return await client.post(
                f"/organizations/{org_id}/transfer-ownership",
                headers=_auth(o),
                json={"target_user_id": str(t)},
            )

        task1 = task2 = None
        try:
            task1 = asyncio.create_task(do_transfer())
            await asyncio.wait_for(ctrl.lock_held.wait(), timeout=5.0)
            task2 = asyncio.create_task(do_transfer())
            await ctrl.wait_second_blocked(Session)
            ctrl.release_gate.set()
            r1, r2 = await asyncio.gather(task1, task2)
            task1 = task2 = None
        finally:
            ctrl.release_gate.set()
            for task in (task1, task2):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [200, 403], (r1.status_code, r1.text, r2.status_code, r2.text)

        state = await _org_state(Session, org_id)
        assert state["owner_user_id"] == t
        assert len(state["owners"]) == 1
        assert state["owners"][0].user_id == t
        assert state["by_user"].get(o) == "admin"
        assert await _audit_success_count(Session, org_id, "ownership_transferred") == 1


@pytest.mark.asyncio
async def test_c2_revoke_target_before_transfer_serialized(monkeypatch):
    """C2a: revoke T completes first → transfer 404; O remains owner."""
    from app.api import organizations as org_api

    async with _http_harness() as (Session, client, _app):
        ctx = await _seed(Session)
        org_id = ctx["org_id"]
        o, t = ctx["owner"], ctx["target"]
        tid = ctx["member_ids"]["target"]

        ctrl = _LockHoldController()
        ctrl.install(monkeypatch, org_api, org_api._lock_active_org)

        async def do_revoke():
            return await client.delete(
                f"/organizations/{org_id}/members/{tid}",
                headers=_auth(o),
            )

        async def do_transfer():
            return await client.post(
                f"/organizations/{org_id}/transfer-ownership",
                headers=_auth(o),
                json={"target_user_id": str(t)},
            )

        t_rev = t_tr = None
        try:
            t_rev = asyncio.create_task(do_revoke())
            await asyncio.wait_for(ctrl.lock_held.wait(), timeout=5.0)
            t_tr = asyncio.create_task(do_transfer())
            await ctrl.wait_second_blocked(Session)
            ctrl.release_gate.set()
            r_rev, r_tr = await asyncio.gather(t_rev, t_tr)
            t_rev = t_tr = None
        finally:
            ctrl.release_gate.set()
            for task in (t_rev, t_tr):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        assert r_rev.status_code == 204, r_rev.text
        assert r_tr.status_code == 404, r_tr.text

        state = await _org_state(Session, org_id)
        assert state["owner_user_id"] == o
        assert len(state["owners"]) == 1
        assert state["owners"][0].user_id == o
        assert t not in state["by_user"]
        assert await _audit_success_count(Session, org_id, "member_revoked") == 1
        assert await _audit_success_count(Session, org_id, "ownership_transferred") == 0


@pytest.mark.asyncio
async def test_c2_transfer_before_revoke_new_owner_409(monkeypatch):
    """C2b: transfer first → revoke of new owner T returns 409."""
    from app.api import organizations as org_api

    async with _http_harness() as (Session, client, _app):
        ctx = await _seed(Session)
        org_id = ctx["org_id"]
        o, t = ctx["owner"], ctx["target"]
        tid = ctx["member_ids"]["target"]

        ctrl = _LockHoldController()
        ctrl.install(monkeypatch, org_api, org_api._lock_active_org)

        async def do_transfer():
            return await client.post(
                f"/organizations/{org_id}/transfer-ownership",
                headers=_auth(o),
                json={"target_user_id": str(t)},
            )

        async def do_revoke():
            return await client.delete(
                f"/organizations/{org_id}/members/{tid}",
                headers=_auth(o),
            )

        t_tr = t_rev = None
        try:
            t_tr = asyncio.create_task(do_transfer())
            await asyncio.wait_for(ctrl.lock_held.wait(), timeout=5.0)
            t_rev = asyncio.create_task(do_revoke())
            await ctrl.wait_second_blocked(Session)
            ctrl.release_gate.set()
            r_tr, r_rev = await asyncio.gather(t_tr, t_rev)
            t_tr = t_rev = None
        finally:
            ctrl.release_gate.set()
            for task in (t_tr, t_rev):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        assert r_tr.status_code == 200, r_tr.text
        assert r_rev.status_code == 409, r_rev.text

        state = await _org_state(Session, org_id)
        assert state["owner_user_id"] == t
        assert len(state["owners"]) == 1
        assert state["owners"][0].user_id == t
        assert state["by_user"].get(o) == "admin"
        assert await _audit_success_count(Session, org_id, "ownership_transferred") == 1
        assert await _audit_success_count(Session, org_id, "member_revoked") == 0


@pytest.mark.asyncio
async def test_c4_concurrent_duplicate_member_add(monkeypatch):
    """C4: dual add same user U → {201, 409}; one row; member_added == 1."""
    from app.api import organizations as org_api

    async with _http_harness() as (Session, client, _app):
        ctx = await _seed(Session)
        org_id = ctx["org_id"]
        o, u = ctx["owner"], ctx["outsider"]

        ctrl = _LockHoldController()
        ctrl.install(monkeypatch, org_api, org_api._lock_active_org)

        async def do_add():
            return await client.post(
                f"/organizations/{org_id}/members",
                headers=_auth(o),
                json={"user_id": str(u), "role": "viewer"},
            )

        t1 = t2 = None
        try:
            t1 = asyncio.create_task(do_add())
            await asyncio.wait_for(ctrl.lock_held.wait(), timeout=5.0)
            t2 = asyncio.create_task(do_add())
            await ctrl.wait_second_blocked(Session)
            ctrl.release_gate.set()
            r1, r2 = await asyncio.gather(t1, t2)
            t1 = t2 = None
        finally:
            ctrl.release_gate.set()
            for task in (t1, t2):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [201, 409], (r1.status_code, r1.text, r2.status_code, r2.text)

        state = await _org_state(Session, org_id)
        assert state["by_user"].get(u) == "viewer"
        assert state["member_count"] == 3
        assert await _audit_success_count(Session, org_id, "member_added") == 1


@pytest.mark.asyncio
async def test_transfer_audit_failure_rolls_back(monkeypatch):
    """Audit writer failure during transfer rolls back ownership mutation."""
    async with _http_harness() as (Session, client, _app):
        ctx = await _seed(Session)
        org_id = ctx["org_id"]
        o, t = ctx["owner"], ctx["target"]

        async def _boom(*args, **kwargs):
            raise RuntimeError("audit_forced_failure")

        monkeypatch.setattr("app.api.organizations.record_security_audit", _boom)

        with pytest.raises(RuntimeError, match="audit_forced_failure"):
            await client.post(
                f"/organizations/{org_id}/transfer-ownership",
                headers=_auth(o),
                json={"target_user_id": str(t)},
            )

        state = await _org_state(Session, org_id)
        assert state["owner_user_id"] == o
        assert state["by_user"].get(o) == "owner"
        assert state["by_user"].get(t) == "editor"
        assert len(state["owners"]) == 1
        assert state["owners"][0].user_id == o
        assert await _audit_success_count(Session, org_id, "ownership_transferred") == 0
