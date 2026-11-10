"""Phase C.2.4 — organization-scoped RBAC HTTP matrix (PostgreSQL 16).

Real FastAPI ASGI requests. No mocked authorization decisions.
NullPool harness isolates async engines per event loop (same pattern as C.2.3.2).
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set — C.2.4 RBAC DEFERRED (INFRA SCOPE)",
    ),
]


def _token_for(user_id: uuid.UUID) -> str:
    from app.core.security import create_access_token
    return create_access_token(str(user_id), token_version=0)


def _auth(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {_token_for(user_id)}"}


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
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    try:
        yield Session, client
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        await engine.dispose()


async def _seed_rbac(Session) -> dict:
    from app.core.security import hash_password
    from app.models.organization import Organization, OrganizationMember
    from app.models.project import Asset, Project
    from app.models.user import User

    owner = uuid.uuid4()
    admin = uuid.uuid4()
    editor = uuid.uuid4()
    viewer = uuid.uuid4()
    outsider = uuid.uuid4()
    owner_b = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    asset_a = uuid.uuid4()
    asset_b = uuid.uuid4()

    async with Session() as session:
        async with session.begin():
            for uid, label in [
                (owner, "owner"), (admin, "admin"), (editor, "editor"),
                (viewer, "viewer"), (outsider, "outsider"), (owner_b, "owner_b"),
            ]:
                session.add(User(
                    id=uid, email=f"c24_{label}_{uid.hex[:8]}@example.com",
                    password_hash=hash_password("TestPass123!"), full_name=label, is_active=True,
                ))
            await session.flush()
            session.add(Organization(id=org_a, name="Org A RBAC", slug=f"c24-a-{org_a.hex[:8]}", owner_user_id=owner))
            session.add(Organization(id=org_b, name="Org B RBAC", slug=f"c24-b-{org_b.hex[:8]}", owner_user_id=owner_b))
            await session.flush()
            for uid, role in [(owner, "owner"), (admin, "admin"), (editor, "editor"), (viewer, "viewer")]:
                session.add(OrganizationMember(organization_id=org_a, user_id=uid, role=role))
            session.add(OrganizationMember(organization_id=org_b, user_id=owner_b, role="owner"))
            session.add(Project(id=project_a, organization_id=org_a, name="Project A", description=None, status="draft", created_by=owner))
            session.add(Project(id=project_b, organization_id=org_b, name="Project B", description=None, status="draft", created_by=owner_b))
            await session.flush()
            session.add(Asset(id=asset_a, project_id=project_a, filename="a.mp4", type="video", mime_type="video/mp4", storage_key=f"local/{org_a}/{project_a}/a.mp4", size_bytes=100))
            session.add(Asset(id=asset_b, project_id=project_b, filename="b.mp4", type="video", mime_type="video/mp4", storage_key=f"local/{org_b}/{project_b}/b.mp4", size_bytes=100))

    return {
        "owner": owner, "admin": admin, "editor": editor, "viewer": viewer,
        "outsider": outsider, "owner_b": owner_b, "org_a": org_a, "org_b": org_b,
        "project_a": project_a, "project_b": project_b, "asset_a": asset_a, "asset_b": asset_b,
    }


def test_rbac_role_has_matrix():
    from app.services.rbac import Permission, role_has
    assert role_has("viewer", Permission.PROJECT_READ)
    assert not role_has("viewer", Permission.PROJECT_UPDATE)
    assert not role_has("viewer", Permission.PROJECT_DELETE)
    assert not role_has("viewer", Permission.ASSET_WRITE)
    assert role_has("editor", Permission.PROJECT_UPDATE)
    assert role_has("editor", Permission.ASSET_WRITE)
    assert not role_has("editor", Permission.PROJECT_DELETE)
    assert not role_has("editor", Permission.ORG_MEMBERS_MANAGE)
    assert role_has("admin", Permission.PROJECT_DELETE)
    assert role_has("admin", Permission.ORG_ASSIGN_EDITOR_VIEWER)
    assert not role_has("admin", Permission.ORG_ASSIGN_ADMIN)
    assert not role_has("admin", Permission.ORG_TRANSFER_OWNERSHIP)
    assert role_has("owner", Permission.ORG_ASSIGN_ADMIN)
    assert role_has("owner", Permission.ORG_TRANSFER_OWNERSHIP)
    assert role_has("owner", Permission.ORG_DELETE)


def test_rbac_normalize_role_least_privilege():
    from app.services.rbac import normalize_role
    assert normalize_role("Owner") == "owner"
    assert normalize_role("ADMIN") == "admin"
    assert normalize_role("editor") == "editor"
    assert normalize_role("viewer") == "viewer"
    assert normalize_role(None) == "viewer"
    assert normalize_role("") == "viewer"
    assert normalize_role("  ") == "viewer"
    assert normalize_role("superuser") == "viewer"
    assert normalize_role("root") == "viewer"
    assert normalize_role("member") == "viewer"


def test_rbac_assert_role_assignment():
    from fastapi import HTTPException
    from app.services.rbac import assert_role_assignment_allowed
    assert_role_assignment_allowed("owner", "admin")
    assert_role_assignment_allowed("owner", "editor")
    assert_role_assignment_allowed("owner", "viewer")
    assert_role_assignment_allowed("admin", "editor")
    assert_role_assignment_allowed("admin", "viewer")
    with pytest.raises(HTTPException) as ei:
        assert_role_assignment_allowed("admin", "admin")
    assert ei.value.status_code == 403
    with pytest.raises(HTTPException) as ei:
        assert_role_assignment_allowed("admin", "owner")
    assert ei.value.status_code == 403
    with pytest.raises(HTTPException) as ei:
        assert_role_assignment_allowed("editor", "viewer")
    assert ei.value.status_code == 403
    with pytest.raises(HTTPException) as ei:
        assert_role_assignment_allowed("viewer", "viewer")
    assert ei.value.status_code == 403
    with pytest.raises(HTTPException) as ei:
        assert_role_assignment_allowed("owner", "owner")
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_rbac_all_roles_can_read_project():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        for role in ("owner", "admin", "editor", "viewer"):
            r = await client.get(f"/projects/{ctx['project_a']}", headers=_auth(ctx[role]))
            assert r.status_code == 200, f"{role}: {r.text}"


@pytest.mark.asyncio
async def test_rbac_outsider_and_cross_tenant_read_404():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        r = await client.get(f"/projects/{ctx['project_a']}", headers=_auth(ctx["outsider"]))
        assert r.status_code == 404, r.text
        r2 = await client.get(f"/projects/{ctx['project_a']}", headers=_auth(ctx["owner_b"]))
        assert r2.status_code == 404, r2.text


@pytest.mark.asyncio
async def test_rbac_owner_admin_editor_create_viewer_denied():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        for role in ("owner", "admin", "editor"):
            r = await client.post("/projects", headers=_auth(ctx[role]), json={
                "organization_id": str(ctx["org_a"]), "name": f"Created-by-{role}", "description": None,
            })
            assert r.status_code == 201, f"{role}: {r.text}"
        r = await client.post("/projects", headers=_auth(ctx["viewer"]), json={
            "organization_id": str(ctx["org_a"]), "name": "Viewer-should-fail", "description": None,
        })
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_rbac_viewer_cannot_update_project():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        r = await client.patch(f"/projects/{ctx['project_a']}", headers=_auth(ctx["viewer"]), json={"name": "Hacked"})
        assert r.status_code == 403, r.text
        r2 = await client.patch(f"/projects/{ctx['project_a']}", headers=_auth(ctx["editor"]), json={"name": "Editor-ok"})
        assert r2.status_code == 200, r2.text


@pytest.mark.asyncio
async def test_rbac_editor_cannot_delete_admin_owner_can():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        from app.models.project import Project
        r = await client.delete(f"/projects/{ctx['project_a']}", headers=_auth(ctx["editor"]))
        assert r.status_code == 403, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p is not None and p.deleted_at is None
        r_v = await client.delete(f"/projects/{ctx['project_a']}", headers=_auth(ctx["viewer"]))
        assert r_v.status_code == 403, r_v.text
        r2 = await client.delete(f"/projects/{ctx['project_a']}", headers=_auth(ctx["admin"]))
        assert r2.status_code == 204, r2.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p is not None and p.deleted_at is not None


@pytest.mark.asyncio
async def test_rbac_viewer_cannot_upload_editor_can():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        files = {"file": ("clip.mp4", b"fake-video-bytes", "video/mp4")}
        data = {"asset_type": "video"}
        r = await client.post(f"/projects/{ctx['project_a']}/assets/upload", headers=_auth(ctx["viewer"]), files=files, data=data)
        assert r.status_code == 403, r.text
        files2 = {"file": ("clip2.mp4", b"fake-video-bytes-2", "video/mp4")}
        r2 = await client.post(f"/projects/{ctx['project_a']}/assets/upload", headers=_auth(ctx["editor"]), files=files2, data=data)
        assert r2.status_code != 403, r2.text
        assert r2.status_code in (201, 400, 413, 500), r2.text


@pytest.mark.asyncio
async def test_rbac_timeline_viewer_read_editor_write():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        r = await client.post(f"/projects/{ctx['project_a']}/timelines", headers=_auth(ctx["viewer"]), json={"name": "Main", "fps": 30.0})
        assert r.status_code == 403, r.text
        r2 = await client.post(f"/projects/{ctx['project_a']}/timelines", headers=_auth(ctx["editor"]), json={"name": "Main", "fps": 30.0})
        assert r2.status_code == 201, r2.text
        timeline_id = r2.json()["id"]
        r3 = await client.get(f"/projects/{ctx['project_a']}/timelines", headers=_auth(ctx["viewer"]))
        assert r3.status_code == 200, r3.text
        assert any(t["id"] == timeline_id for t in r3.json())
        r4 = await client.get(f"/projects/{ctx['project_a']}/timelines", headers=_auth(ctx["outsider"]))
        assert r4.status_code == 404, r4.text
        r5 = await client.post(f"/timelines/{timeline_id}/tracks", headers=_auth(ctx["viewer"]), json={"name": "X", "track_type": "video", "order_index": 2})
        assert r5.status_code == 403, r5.text


@pytest.mark.asyncio
async def test_rbac_role_downgrade_immediately_blocks_update():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        from app.models.organization import OrganizationMember
        from sqlalchemy import select
        r = await client.patch(f"/projects/{ctx['project_a']}", headers=_auth(ctx["editor"]), json={"name": "Before-downgrade"})
        assert r.status_code == 200, r.text
        async with Session() as session:
            async with session.begin():
                result = await session.execute(select(OrganizationMember).where(
                    OrganizationMember.organization_id == ctx["org_a"],
                    OrganizationMember.user_id == ctx["editor"],
                ))
                mem = result.scalar_one()
                mem.role = "viewer"
        r2 = await client.patch(f"/projects/{ctx['project_a']}", headers=_auth(ctx["editor"]), json={"name": "After-downgrade"})
        assert r2.status_code == 403, r2.text


@pytest.mark.asyncio
async def test_rbac_membership_revocation_immediately_blocks_read():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        from app.models.organization import OrganizationMember
        from sqlalchemy import delete
        r = await client.get(f"/projects/{ctx['project_a']}", headers=_auth(ctx["viewer"]))
        assert r.status_code == 200, r.text
        async with Session() as session:
            async with session.begin():
                await session.execute(delete(OrganizationMember).where(
                    OrganizationMember.organization_id == ctx["org_a"],
                    OrganizationMember.user_id == ctx["viewer"],
                ))
        r2 = await client.get(f"/projects/{ctx['project_a']}", headers=_auth(ctx["viewer"]))
        assert r2.status_code == 404, r2.text


@pytest.mark.asyncio
async def test_rbac_soft_deleted_asset_download_404():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        from app.models.project import Asset
        async with Session() as session:
            async with session.begin():
                asset = await session.get(Asset, ctx["asset_a"])
                asset.deleted_at = datetime.now(timezone.utc)
        r = await client.get(f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content", headers=_auth(ctx["owner"]))
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_rbac_cross_tenant_asset_idor_404():
    async with _http_harness() as (Session, client):
        ctx = await _seed_rbac(Session)
        r = await client.get(f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content", headers=_auth(ctx["owner_b"]))
        assert r.status_code == 404, r.text
        r2 = await client.get(f"/projects/{ctx['project_a']}/assets/{ctx['asset_b']}/content", headers=_auth(ctx["owner"]))
        assert r2.status_code == 404, r2.text
