"""C.2.3.2 HTTP multi-tenant authorization (PostgreSQL 16).

Real FastAPI ASGI. No mocked auth. NullPool harness per event loop.
POLICY (C.2.4): editor lacks project:delete → 403; non-members → 404.
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

from tests.c231_pg_helpers import _seed_two_tenants

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set — C.2.3.2 HTTP multi-tenant auth DEFERRED (INFRA SCOPE)",
    ),
]

def _token_for(user_id: uuid.UUID) -> str:
    from app.core.security import create_access_token

    return create_access_token(str(user_id), token_version=0)

def _auth(headers_base: dict, user_id: uuid.UUID) -> dict:
    h = dict(headers_base)
    h["Authorization"] = f"Bearer {_token_for(user_id)}"
    return h

@asynccontextmanager
async def _http_harness():
    """Bind engine + FastAPI get_db override to the *current* event loop.

    NullPool avoids retaining asyncpg connections across loop boundaries.
    Dependency override ensures ASGI requests never touch the module-level
    process-global engine created at import time in app.db.session.
    """
    from app.db.session import get_db
    from app.main import create_app

    engine = create_async_engine(
        DATABASE_URL,
        poolclass=NullPool,
        pool_pre_ping=True,
    )
    Session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _override_get_db():
        async with Session() as session:
            session.info.setdefault("pending_storage_keys", [])
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

async def _seed(Session):
    """Commit two-tenant fixture through the harness session factory."""
    async with Session() as session:
        async with session.begin():
            return await _seed_two_tenants(session)

@pytest.mark.asyncio
async def test_http_owner_a_can_read_project_a():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == str(ctx["project_a"])
        assert body["organization_id"] == str(ctx["org_a"])
        assert "name" in body

@pytest.mark.asyncio
async def test_http_editor_a_can_read_project_a_membership_contract():
    """Current contract: membership alone grants read; role is not evaluated."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["member_a"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == str(ctx["project_a"])

@pytest.mark.asyncio
async def test_http_outsider_cannot_read_project_a():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["outsider"]),
        )
        assert r.status_code == 404, r.text
        body = r.json()
        assert body.get("detail")

@pytest.mark.asyncio
async def test_http_owner_b_cannot_read_project_a():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_b"]),
        )
        assert r.status_code == 404, r.text

@pytest.mark.asyncio
async def test_http_owner_a_can_update_project_a():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        new_name = f"Updated-by-owner-{uuid.uuid4().hex[:6]}"
        r = await client.patch(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_a"]),
            json={"name": new_name},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == new_name
        async with Session() as session:
            from app.models.project import Project

            p = await session.get(Project, ctx["project_a"])
            assert p is not None
            assert p.name == new_name

@pytest.mark.asyncio
async def test_http_editor_a_can_update_project_a_membership_contract():
    """Documented current contract: editor membership may update (no role gate)."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        new_name = f"Updated-by-editor-{uuid.uuid4().hex[:6]}"
        r = await client.patch(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["member_a"]),
            json={"name": new_name},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == new_name

@pytest.mark.asyncio
async def test_http_outsider_cannot_update_project_a_no_db_mutation():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Project

        async with Session() as session:
            original = (await session.get(Project, ctx["project_a"])).name
        r = await client.patch(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["outsider"]),
            json={"name": "HACKED-BY-OUTSIDER"},
        )
        assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.name == original
            assert p.deleted_at is None

@pytest.mark.asyncio
async def test_http_owner_b_cannot_update_project_a_no_db_mutation():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Project

        async with Session() as session:
            original = (await session.get(Project, ctx["project_a"])).name
        r = await client.patch(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_b"]),
            json={"name": "HACKED-BY-OWNER-B"},
        )
        assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.name == original

@pytest.mark.asyncio
async def test_http_outsider_cannot_delete_project_a_deleted_at_unchanged():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Project

        r = await client.delete(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["outsider"]),
        )
        assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.deleted_at is None

@pytest.mark.asyncio
async def test_http_owner_b_cannot_delete_project_a_deleted_at_unchanged():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Project

        r = await client.delete(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_b"]),
        )
        assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.deleted_at is None

@pytest.mark.asyncio
async def test_http_owner_a_soft_delete_then_read_returns_404():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Project

        r = await client.delete(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r.status_code == 204, r.text
        r2 = await client.get(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r2.status_code == 404, r2.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p is not None
            assert p.deleted_at is not None

@pytest.mark.asyncio
async def test_http_editor_a_soft_delete_denied_by_rbac():
    """C.2.4 policy: editor lacks project:delete → 403; deleted_at unchanged."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Project

        r = await client.delete(
            f"/projects/{ctx['project_a']}",
            headers=_auth({}, ctx["member_a"]),
        )
        assert r.status_code == 403, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.deleted_at is None

@pytest.mark.asyncio
async def test_http_owner_a_lists_only_project_a_assets():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r.status_code == 200, r.text
        ids = {item["id"] for item in r.json()}
        assert str(ctx["asset_a"]) in ids
        assert str(ctx["asset_b"]) not in ids

@pytest.mark.asyncio
async def test_http_editor_a_lists_project_a_assets_membership_contract():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets",
            headers=_auth({}, ctx["member_a"]),
        )
        assert r.status_code == 200, r.text
        ids = {item["id"] for item in r.json()}
        assert str(ctx["asset_a"]) in ids
        assert str(ctx["asset_b"]) not in ids

@pytest.mark.asyncio
async def test_http_outsider_cannot_list_project_a_assets():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets",
            headers=_auth({}, ctx["outsider"]),
        )
        assert r.status_code == 404, r.text

@pytest.mark.asyncio
async def test_http_owner_b_cannot_list_project_a_assets():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets",
            headers=_auth({}, ctx["owner_b"]),
        )
        assert r.status_code == 404, r.text

@pytest.mark.asyncio
async def test_http_cross_project_asset_id_rejected_on_download():
    """Valid asset_b id under project_a path must not bypass authorization."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_b']}/content",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r.status_code == 404, r.text
        r2 = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth({}, ctx["outsider"]),
        )
        assert r2.status_code == 404, r2.text
        r3 = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth({}, ctx["owner_b"]),
        )
        assert r3.status_code == 404, r3.text

@pytest.mark.asyncio
async def test_http_authorized_download_no_leak_on_missing_storage():
    """Owner may pass auth gate; missing storage object returns 404 without path leak."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r.status_code in (200, 404), r.text
        if r.status_code == 404:
            assert "local/" not in r.text
            assert "storage_key" not in r.text.lower()
        if r.status_code == 200:
            assert "X-Storage-Key" not in r.headers

@pytest.mark.asyncio
async def test_http_outsider_download_denied_no_storage_leak():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth({}, ctx["outsider"]),
        )
        assert r.status_code == 404, r.text
        assert "local/" not in r.text
        assert "storage_key" not in r.text.lower()
        assert "signed" not in r.text.lower()

@pytest.mark.asyncio
async def test_http_owner_b_download_project_a_asset_denied():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth({}, ctx["owner_b"]),
        )
        assert r.status_code == 404, r.text
        assert "local/" not in r.text

@pytest.mark.asyncio
async def test_http_soft_deleted_asset_download_denied():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        from app.models.project import Asset

        async with Session() as session:
            async with session.begin():
                asset = await session.get(Asset, ctx["asset_a"])
                asset.deleted_at = datetime.now(timezone.utc)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r.status_code == 404, r.text
        assert "local/" not in r.text

@pytest.mark.asyncio
async def test_http_list_org_projects_outsider_forbidden():
    """Org-scoped list uses _require_org_member → 403 for non-members."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        r = await client.get(
            f"/organizations/{ctx['org_a']}/projects",
            headers=_auth({}, ctx["outsider"]),
        )
        assert r.status_code == 403, r.text
        r2 = await client.get(
            f"/organizations/{ctx['org_a']}/projects",
            headers=_auth({}, ctx["owner_b"]),
        )
        assert r2.status_code == 403, r2.text
        r3 = await client.get(
            f"/organizations/{ctx['org_a']}/projects",
            headers=_auth({}, ctx["owner_a"]),
        )
        assert r3.status_code == 200, r3.text
        ids = {p["id"] for p in r3.json()}
        assert str(ctx["project_a"]) in ids
        assert str(ctx["project_b"]) not in ids
