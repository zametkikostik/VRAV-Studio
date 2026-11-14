"""Phase C.2.5 Stage B — organization member lifecycle HTTP (PostgreSQL 16).

Real FastAPI ASGI + real DB sessions. No mocked authorization.
Stage B.1 concurrency/cardinality certification is out of scope.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set — C.2.5 lifecycle DEFERRED (INFRA SCOPE)",
    ),
]


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
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        yield Session, client
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        await engine.dispose()


async def _seed(Session) -> dict:
    from app.core.security import hash_password
    from app.models.organization import Organization, OrganizationMember
    from app.models.project import Project
    from app.models.user import User

    owner, admin, editor, viewer, outsider, inactive = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    org_a = uuid.uuid4()
    proj = uuid.uuid4()
    ids = {}
    async with Session() as s:
        async with s.begin():
            for uid, email, active in [
                (owner, f"o_{owner.hex[:8]}@ex.com", True),
                (admin, f"a_{admin.hex[:8]}@ex.com", True),
                (editor, f"e_{editor.hex[:8]}@ex.com", True),
                (viewer, f"v_{viewer.hex[:8]}@ex.com", True),
                (outsider, f"x_{outsider.hex[:8]}@ex.com", True),
                (inactive, f"i_{inactive.hex[:8]}@ex.com", False),
            ]:
                s.add(
                    User(
                        id=uid,
                        email=email,
                        password_hash=hash_password("x"),
                        is_active=active,
                    )
                )
            await s.flush()
            s.add(
                Organization(
                    id=org_a,
                    name="Life A",
                    slug=f"life-a-{org_a.hex[:8]}",
                    owner_user_id=owner,
                )
            )
            await s.flush()
            for uid, role in [
                (owner, "owner"),
                (admin, "admin"),
                (editor, "editor"),
                (viewer, "viewer"),
            ]:
                mid = uuid.uuid4()
                s.add(
                    OrganizationMember(
                        id=mid, organization_id=org_a, user_id=uid, role=role
                    )
                )
                ids[role] = mid
            s.add(
                Project(
                    id=proj,
                    organization_id=org_a,
                    name="P",
                    description=None,
                    status="draft",
                    created_by=owner,
                )
            )
    return {
        "owner": owner,
        "admin": admin,
        "editor": editor,
        "viewer": viewer,
        "outsider": outsider,
        "inactive": inactive,
        "org_a": org_a,
        "proj": proj,
        "member_ids": ids,
    }


async def _audit_count(Session, org_id, event_type: str) -> int:
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


@pytest.mark.asyncio
async def test_list_members_owner_admin_ok_others_denied():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/organizations/{ctx['org_a']}/members", headers=_auth(ctx["owner"])
        )
        assert r.status_code == 200, r.text
        assert len(r.json()) == 4
        r2 = await client.get(
            f"/organizations/{ctx['org_a']}/members", headers=_auth(ctx["admin"])
        )
        assert r2.status_code == 200
        for uid in (ctx["editor"], ctx["viewer"], ctx["outsider"]):
            rr = await client.get(
                f"/organizations/{ctx['org_a']}/members", headers=_auth(uid)
            )
            assert rr.status_code == 403, uid


@pytest.mark.asyncio
async def test_add_member_and_duplicate_and_inactive_and_invalid_role():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        # owner assigns editor role to outsider
        r = await client.post(
            f"/organizations/{ctx['org_a']}/members",
            headers=_auth(ctx["owner"]),
            json={"user_id": str(ctx["outsider"]), "role": "editor"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["role"] == "editor"
        assert body["user_id"] == str(ctx["outsider"])
        assert await _audit_count(Session, ctx["org_a"], "member_added") >= 1
        # duplicate
        r2 = await client.post(
            f"/organizations/{ctx['org_a']}/members",
            headers=_auth(ctx["owner"]),
            json={"user_id": str(ctx["outsider"]), "role": "viewer"},
        )
        assert r2.status_code == 409
        # inactive
        r3 = await client.post(
            f"/organizations/{ctx['org_a']}/members",
            headers=_auth(ctx["owner"]),
            json={"user_id": str(ctx["inactive"]), "role": "viewer"},
        )
        assert r3.status_code == 404
        # invalid role
        r4 = await client.post(
            f"/organizations/{ctx['org_a']}/members",
            headers=_auth(ctx["owner"]),
            json={"user_id": str(uuid.uuid4()), "role": "superuser"},
        )
        assert r4.status_code in (400, 404)


@pytest.mark.asyncio
async def test_admin_cannot_assign_admin_owner_can():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        # need a free active user — create one
        from app.core.security import hash_password
        from app.models.user import User

        newbie = uuid.uuid4()
        async with Session() as s:
            async with s.begin():
                s.add(
                    User(
                        id=newbie,
                        email=f"n_{newbie.hex[:8]}@ex.com",
                        password_hash=hash_password("x"),
                        is_active=True,
                    )
                )
        r = await client.post(
            f"/organizations/{ctx['org_a']}/members",
            headers=_auth(ctx["admin"]),
            json={"user_id": str(newbie), "role": "admin"},
        )
        assert r.status_code == 403, r.text
        r2 = await client.post(
            f"/organizations/{ctx['org_a']}/members",
            headers=_auth(ctx["owner"]),
            json={"user_id": str(newbie), "role": "admin"},
        )
        assert r2.status_code == 201, r2.text


@pytest.mark.asyncio
async def test_patch_role_idempotent_and_owner_protection():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        mid = ctx["member_ids"]["editor"]
        r = await client.patch(
            f"/organizations/{ctx['org_a']}/members/{mid}",
            headers=_auth(ctx["owner"]),
            json={"role": "editor"},
        )
        assert r.status_code == 200
        assert r.json()["role"] == "editor"
        # change to viewer
        r2 = await client.patch(
            f"/organizations/{ctx['org_a']}/members/{mid}",
            headers=_auth(ctx["owner"]),
            json={"role": "viewer"},
        )
        assert r2.status_code == 200
        assert r2.json()["role"] == "viewer"
        assert await _audit_count(Session, ctx["org_a"], "member_role_changed") >= 1
        # owner protection
        omid = ctx["member_ids"]["owner"]
        r3 = await client.patch(
            f"/organizations/{ctx['org_a']}/members/{omid}",
            headers=_auth(ctx["owner"]),
            json={"role": "admin"},
        )
        assert r3.status_code == 409
        # cannot assign owner
        r4 = await client.patch(
            f"/organizations/{ctx['org_a']}/members/{mid}",
            headers=_auth(ctx["owner"]),
            json={"role": "owner"},
        )
        assert r4.status_code == 403
        # admin cannot assign admin
        r5 = await client.patch(
            f"/organizations/{ctx['org_a']}/members/{mid}",
            headers=_auth(ctx["admin"]),
            json={"role": "admin"},
        )
        assert r5.status_code == 403


@pytest.mark.asyncio
async def test_revoke_policies_and_owner_self_protection():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.core.security import hash_password
        from app.models.user import User
        from app.models.organization import OrganizationMember

        # second admin (other admin) for non-self revoke denial
        other_admin = uuid.uuid4()
        other_mid = uuid.uuid4()
        async with Session() as s:
            async with s.begin():
                s.add(
                    User(
                        id=other_admin,
                        email=f"oa_{other_admin.hex[:8]}@ex.com",
                        password_hash=hash_password("x"),
                        is_active=True,
                    )
                )
                await s.flush()
                s.add(
                    OrganizationMember(
                        id=other_mid,
                        organization_id=ctx["org_a"],
                        user_id=other_admin,
                        role="admin",
                    )
                )
        # admin can revoke editor
        r = await client.delete(
            f"/organizations/{ctx['org_a']}/members/{ctx['member_ids']['editor']}",
            headers=_auth(ctx["admin"]),
        )
        assert r.status_code == 204, r.text
        assert await _audit_count(Session, ctx["org_a"], "member_revoked") >= 1
        # admin cannot revoke another admin
        r2 = await client.delete(
            f"/organizations/{ctx['org_a']}/members/{other_mid}",
            headers=_auth(ctx["admin"]),
        )
        assert r2.status_code == 403, r2.text
        # self-revoke allowed for admin
        r3 = await client.delete(
            f"/organizations/{ctx['org_a']}/members/{ctx['member_ids']['admin']}",
            headers=_auth(ctx["admin"]),
        )
        assert r3.status_code == 204, r3.text
        # owner cannot self-revoke
        r4 = await client.delete(
            f"/organizations/{ctx['org_a']}/members/{ctx['member_ids']['owner']}",
            headers=_auth(ctx["owner"]),
        )
        assert r4.status_code == 409


@pytest.mark.asyncio
async def test_transfer_ownership_and_invariant():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.post(
            f"/organizations/{ctx['org_a']}/transfer-ownership",
            headers=_auth(ctx["owner"]),
            json={"target_user_id": str(ctx["admin"])},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["new_owner_user_id"] == str(ctx["admin"])
        assert data["previous_owner_new_role"] == "admin"
        assert await _audit_count(Session, ctx["org_a"], "ownership_transferred") == 1
        from app.models.organization import Organization, OrganizationMember

        async with Session() as s:
            org = await s.get(Organization, ctx["org_a"])
            assert org.owner_user_id == ctx["admin"]
            res = await s.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == ctx["org_a"]
                )
            )
            owners = [m for m in res.scalars().all() if m.role == "owner"]
            assert len(owners) == 1
            assert owners[0].user_id == ctx["admin"]
        # no-op transfer
        r2 = await client.post(
            f"/organizations/{ctx['org_a']}/transfer-ownership",
            headers=_auth(ctx["admin"]),
            json={"target_user_id": str(ctx["admin"])},
        )
        assert r2.status_code == 409


@pytest.mark.asyncio
async def test_soft_delete_org_and_404_and_project_remains():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.delete(
            f"/organizations/{ctx['org_a']}", headers=_auth(ctx["owner"])
        )
        assert r.status_code == 204, r.text
        assert await _audit_count(Session, ctx["org_a"], "organization_deleted") == 1
        r2 = await client.get(
            f"/organizations/{ctx['org_a']}/members", headers=_auth(ctx["owner"])
        )
        assert r2.status_code == 404
        r3 = await client.get(
            f"/organizations/{ctx['org_a']}", headers=_auth(ctx["owner"])
        )
        assert r3.status_code == 404
        from app.models.project import Project

        async with Session() as s:
            p = await s.get(Project, ctx["proj"])
            assert p is not None
            assert p.organization_id == ctx["org_a"]


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_mutation(monkeypatch):
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)

        async def _boom(*args, **kwargs):
            raise RuntimeError("audit_forced_failure")

        monkeypatch.setattr(
            "app.api.organizations.record_security_audit", _boom
        )
        from app.core.security import hash_password
        from app.models.user import User
        from app.models.organization import OrganizationMember

        newbie = uuid.uuid4()
        async with Session() as s:
            async with s.begin():
                s.add(
                    User(
                        id=newbie,
                        email=f"nb_{newbie.hex[:8]}@ex.com",
                        password_hash=hash_password("x"),
                        is_active=True,
                    )
                )
        with pytest.raises(RuntimeError):
            await client.post(
                f"/organizations/{ctx['org_a']}/members",
                headers=_auth(ctx["owner"]),
                json={"user_id": str(newbie), "role": "viewer"},
            )
        async with Session() as s:
            res = await s.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == ctx["org_a"],
                    OrganizationMember.user_id == newbie,
                )
            )
            assert res.scalar_one_or_none() is None
