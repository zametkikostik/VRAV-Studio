"""Phase C.2.3.2 — HTTP-level multi-tenant authorization verification.

Real FastAPI ASGI requests against real PostgreSQL 16.
Does not mock authorization, sessions, or HTTP responses.
Does not modify production application code.

Policy note (from C.2.3.1 / projects.py):
  _get_project_for_user and assets_upload._project_for_user gate solely on
  OrganizationMember membership + Project.deleted_at IS NULL.
  OrganizationMember.role is NOT evaluated for project/asset access.
  Therefore owner and editor currently share the same project access surface.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from tests.c231_pg_helpers import _engine_session, _seed_two_tenants

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
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


async def _app_client():
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# A. PROJECT READ (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_owner_a_can_read_project_a():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["owner_a"]),
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == str(ctx["project_a"])
            assert body["organization_id"] == str(ctx["org_a"])
            assert "name" in body
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_editor_a_can_read_project_a_membership_contract():
    """Current contract: membership alone grants read; role is not evaluated."""
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["member_a"]),
            )
            assert r.status_code == 200, r.text
            assert r.json()["id"] == str(ctx["project_a"])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_outsider_cannot_read_project_a():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["outsider"]),
            )
            assert r.status_code == 404, r.text
            body = r.json()
            assert body.get("detail")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_b_cannot_read_project_a():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["owner_b"]),
            )
            assert r.status_code == 404, r.text
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# B. PROJECT UPDATE (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_owner_a_can_update_project_a():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        new_name = f"Updated-by-owner-{uuid.uuid4().hex[:6]}"
        async with await _app_client() as client:
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
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_editor_a_can_update_project_a_membership_contract():
    """Documented current contract: editor membership may update (no role gate)."""
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        new_name = f"Updated-by-editor-{uuid.uuid4().hex[:6]}"
        async with await _app_client() as client:
            r = await client.patch(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["member_a"]),
                json={"name": new_name},
            )
            assert r.status_code == 200, r.text
            assert r.json()["name"] == new_name
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_outsider_cannot_update_project_a_no_db_mutation():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        from app.models.project import Project

        async with Session() as session:
            original = (await session.get(Project, ctx["project_a"])).name
        async with await _app_client() as client:
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
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_b_cannot_update_project_a_no_db_mutation():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        from app.models.project import Project

        async with Session() as session:
            original = (await session.get(Project, ctx["project_a"])).name
        async with await _app_client() as client:
            r = await client.patch(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["owner_b"]),
                json={"name": "HACKED-BY-OWNER-B"},
            )
            assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.name == original
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# C. PROJECT DELETE / SOFT-DELETE (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_outsider_cannot_delete_project_a_deleted_at_unchanged():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        from app.models.project import Project

        async with await _app_client() as client:
            r = await client.delete(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["outsider"]),
            )
            assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.deleted_at is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_b_cannot_delete_project_a_deleted_at_unchanged():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        from app.models.project import Project

        async with await _app_client() as client:
            r = await client.delete(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["owner_b"]),
            )
            assert r.status_code == 404, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.deleted_at is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_a_soft_delete_then_read_returns_404():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        from app.models.project import Project

        async with await _app_client() as client:
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
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_editor_a_soft_delete_membership_contract():
    """Current contract: editor may soft-delete (membership-only gate)."""
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        from app.models.project import Project

        async with await _app_client() as client:
            r = await client.delete(
                f"/projects/{ctx['project_a']}",
                headers=_auth({}, ctx["member_a"]),
            )
            assert r.status_code == 204, r.text
        async with Session() as session:
            p = await session.get(Project, ctx["project_a"])
            assert p.deleted_at is not None
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# D. ASSET LIST / IDOR (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_owner_a_lists_only_project_a_assets():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets",
                headers=_auth({}, ctx["owner_a"]),
            )
            assert r.status_code == 200, r.text
            ids = {item["id"] for item in r.json()}
            assert str(ctx["asset_a"]) in ids
            assert str(ctx["asset_b"]) not in ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_editor_a_lists_project_a_assets_membership_contract():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets",
                headers=_auth({}, ctx["member_a"]),
            )
            assert r.status_code == 200, r.text
            ids = {item["id"] for item in r.json()}
            assert str(ctx["asset_a"]) in ids
            assert str(ctx["asset_b"]) not in ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_outsider_cannot_list_project_a_assets():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets",
                headers=_auth({}, ctx["outsider"]),
            )
            assert r.status_code == 404, r.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_b_cannot_list_project_a_assets():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets",
                headers=_auth({}, ctx["owner_b"]),
            )
            assert r.status_code == 404, r.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_cross_project_asset_id_rejected_on_download():
    """Valid asset_b id under project_a path must not bypass authorization."""
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
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
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# E. ASSET DOWNLOAD / CONTENT (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_authorized_download_no_leak_on_missing_storage():
    """Owner may pass auth gate; missing storage object returns 404 without path leak."""
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
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
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_outsider_download_denied_no_storage_leak():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
                headers=_auth({}, ctx["outsider"]),
            )
            assert r.status_code == 404, r.text
            assert "local/" not in r.text
            assert "storage_key" not in r.text.lower()
            assert "signed" not in r.text.lower()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_b_download_project_a_asset_denied():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
                headers=_auth({}, ctx["owner_b"]),
            )
            assert r.status_code == 404, r.text
            assert "local/" not in r.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_soft_deleted_asset_download_denied():
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                from app.models.project import Asset

                asset = await session.get(Asset, ctx["asset_a"])
                asset.deleted_at = datetime.now(timezone.utc)
                await session.flush()
        async with await _app_client() as client:
            r = await client.get(
                f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
                headers=_auth({}, ctx["owner_a"]),
            )
            assert r.status_code == 404, r.text
            assert "local/" not in r.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_list_org_projects_outsider_forbidden():
    """Org-scoped list uses _require_org_member → 403 for non-members."""
    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
        async with await _app_client() as client:
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
    finally:
        await engine.dispose()
