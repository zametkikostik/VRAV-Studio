"""Phase C.2.3.3 — multi-tenant security evidence closure (HTTP + real storage).

Test-only. Calls real FastAPI routes against real PostgreSQL 16.
Uses LocalStorageProvider (STORAGE_BACKEND=local) to plant real object bytes
so authorized download can assert HTTP 200 and exact body content.

Reuses the C.2.3.2 event-loop isolation pattern (NullPool + get_db override).
Does not mock authorization or HTTP responses.
Does not modify production application code.

POLICY DECISION REQUIRED (observed, not changed):
  Project/asset access is membership-only. OrganizationMember.role is not
  evaluated as a separate project-level permission boundary in the covered
  routes. Editor membership currently receives the same project-level access
  surface as owner membership for read/update/delete/download scenarios.
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

# Force local filesystem storage for deterministic put/get in CI
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/vrav-c233-storage")

pytestmark = [
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set — C.2.3.3 security evidence DEFERRED (INFRA SCOPE)",
    ),
]

# Distinct payload markers so cross-tenant leaks are detectable in body text
PAYLOAD_A = b"C233-TENANT-A-PAYLOAD-" + b"\x00\x01\x02" + b"-END-A"
PAYLOAD_B = b"C233-TENANT-B-PAYLOAD-" + b"\xfe\xfd" + b"-END-B"


def _token_for(user_id: uuid.UUID) -> str:
    from app.core.security import create_access_token

    return create_access_token(str(user_id), token_version=0)


def _auth(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {_token_for(user_id)}"}


@asynccontextmanager
async def _http_harness():
    """NullPool engine + get_db override bound to the current event loop."""
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
    async with Session() as session:
        async with session.begin():
            return await _seed_two_tenants(session)


async def _plant_storage(ctx) -> None:
    """Write real object bytes for both tenant assets via production storage API."""
    from app.services.storage import get_storage

    storage = get_storage()
    key_a = f"local/{ctx['asset_a'].hex}/a.mp4"
    key_b = f"local/{ctx['asset_b'].hex}/b.mp4"
    await storage.put(key_a, PAYLOAD_A, content_type="video/mp4")
    await storage.put(key_b, PAYLOAD_B, content_type="video/mp4")


def _assert_no_storage_leak(response) -> None:
    body = response.content if hasattr(response, "content") else b""
    text = body.decode("utf-8", errors="replace")
    assert "storage_key" not in text.lower()
    assert "/tmp/" not in text
    assert "LOCAL_STORAGE" not in text
    assert "AWS_" not in text
    if response.status_code != 200:
        assert "local/" not in text
        assert PAYLOAD_A not in body
        assert PAYLOAD_B not in body


# ---------------------------------------------------------------------------
# A. POSITIVE AUTHORIZED DOWNLOAD (real storage object)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_owner_a_download_returns_200_and_exact_bytes():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth(ctx["owner_a"]),
        )
        assert r.status_code == 200, r.text
        assert r.content == PAYLOAD_A
        assert PAYLOAD_B not in r.content
        assert "X-Storage-Key" not in r.headers
        _assert_no_storage_leak(r)


@pytest.mark.asyncio
async def test_http_editor_a_download_returns_200_membership_contract():
    """Membership-only gate: editor may download same as owner for project A."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth(ctx["member_a"]),
        )
        assert r.status_code == 200, r.text
        assert r.content == PAYLOAD_A
        assert PAYLOAD_B not in r.content


# ---------------------------------------------------------------------------
# B. NEGATIVE CROSS-TENANT / IDOR / SOFT-DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_outsider_download_denied_no_content_leak():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth(ctx["outsider"]),
        )
        assert r.status_code == 404, r.text
        assert r.content != PAYLOAD_A
        assert PAYLOAD_A not in r.content
        assert PAYLOAD_B not in r.content
        _assert_no_storage_leak(r)


@pytest.mark.asyncio
async def test_http_owner_b_cannot_download_owner_a_asset():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth(ctx["owner_b"]),
        )
        assert r.status_code == 404, r.text
        assert PAYLOAD_A not in r.content
        _assert_no_storage_leak(r)


@pytest.mark.asyncio
async def test_http_valid_asset_id_does_not_bypass_project_gate():
    """asset_b under project_a path must 404 even for owner_a (project mismatch)."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_b']}/content",
            headers=_auth(ctx["owner_a"]),
        )
        assert r.status_code == 404, r.text
        assert PAYLOAD_B not in r.content
        assert PAYLOAD_A not in r.content
        _assert_no_storage_leak(r)


@pytest.mark.asyncio
async def test_http_owner_a_cannot_download_via_project_b_path():
    """Valid asset_a id under project_b path must not bypass authorization."""
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_b']}/assets/{ctx['asset_a']}/content",
            headers=_auth(ctx["owner_a"]),
        )
        assert r.status_code == 404, r.text
        assert PAYLOAD_A not in r.content
        _assert_no_storage_leak(r)


@pytest.mark.asyncio
async def test_http_soft_deleted_asset_download_denied_no_content():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        from app.models.project import Asset

        async with Session() as session:
            async with session.begin():
                asset = await session.get(Asset, ctx["asset_a"])
                asset.deleted_at = datetime.now(timezone.utc)
        r = await client.get(
            f"/projects/{ctx['project_a']}/assets/{ctx['asset_a']}/content",
            headers=_auth(ctx["owner_a"]),
        )
        assert r.status_code == 404, r.text
        assert PAYLOAD_A not in r.content
        _assert_no_storage_leak(r)


@pytest.mark.asyncio
async def test_http_outsider_cannot_download_tenant_b_asset():
    async with _http_harness() as (Session, client):
        ctx = await _seed(Session)
        await _plant_storage(ctx)
        r = await client.get(
            f"/projects/{ctx['project_b']}/assets/{ctx['asset_b']}/content",
            headers=_auth(ctx["outsider"]),
        )
        assert r.status_code == 404, r.text
        assert PAYLOAD_B not in r.content
        _assert_no_storage_leak(r)
