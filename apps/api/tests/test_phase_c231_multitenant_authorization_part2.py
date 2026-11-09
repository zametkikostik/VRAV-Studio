"""Phase C.2.3.1 multi-tenant authorization matrix part 2 (readable PostgreSQL tests).

Requires DATABASE_URL (asyncpg → real PostgreSQL). Never mocked sessions.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from tests.c231_pg_helpers import _engine_session, _seed_two_tenants

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL not set — C.2.3.1 multi-tenant PG auth DEFERRED (INFRA SCOPE)",
    ),
]



# ---------------------------------------------------------------------------
# D. Asset-level IDOR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_sees_only_own_project_assets():
    from app.api.projects import _get_project_for_user
    from app.models.project import Asset

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                rows = (
                    await session.execute(
                        select(Asset).where(
                            Asset.project_id == ctx["project_a"],
                            Asset.deleted_at.is_(None),
                        )
                    )
                ).scalars().all()
                ids = {a.id for a in rows}
                assert ctx["asset_a"] in ids
                assert ctx["asset_b"] not in ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_member_sees_assets_under_membership():
    from app.api.projects import _get_project_for_user
    from app.models.project import Asset

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                await _get_project_for_user(session, ctx["member_a"], ctx["project_a"])
                rows = (
                    await session.execute(
                        select(Asset).where(
                            Asset.project_id == ctx["project_a"],
                            Asset.deleted_at.is_(None),
                        )
                    )
                ).scalars().all()
                assert {a.id for a in rows} == {ctx["asset_a"]}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_outsider_cannot_resolve_foreign_asset_via_project_gate():
    """Asset download path requires project membership first; outsider fails at project gate."""
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["outsider"], ctx["project_a"])
                assert ei.value.status_code == 404
                with pytest.raises(HTTPException):
                    await _get_project_for_user(session, ctx["outsider"], ctx["project_b"])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_project_asset_id_not_returned_under_wrong_project():
    """list_assets filters by project_id; asset_b must not appear under project_a."""
    from app.api.projects import _get_project_for_user
    from app.models.project import Asset

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                asset = await session.get(Asset, ctx["asset_b"])
                assert asset is not None
                assert asset.project_id != ctx["project_a"]
                assert asset.project_id == ctx["project_b"]
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# E. Write / delete isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outsider_cannot_soft_delete_foreign_project():
    from app.api.projects import _get_project_for_user
    from app.models.project import Project

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException):
                    await _get_project_for_user(session, ctx["outsider"], ctx["project_a"])
                project = await session.get(Project, ctx["project_a"])
                assert project.deleted_at is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_b_cannot_soft_delete_project_a():
    from app.api.projects import _get_project_for_user
    from app.models.project import Project

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["owner_b"], ctx["project_a"])
                assert ei.value.status_code == 404
                project = await session.get(Project, ctx["project_a"])
                assert project.deleted_at is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_member_soft_delete_is_gated_and_visible_in_db():
    """Under current contract, member may soft-delete; verify DB mutation after auth."""
    from app.api.projects import _get_project_for_user
    from app.models.project import Project

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                project = await _get_project_for_user(session, ctx["member_a"], ctx["project_a"])
                project.deleted_at = datetime.now(timezone.utc)
                await session.flush()
                await session.refresh(project)
                assert project.deleted_at is not None
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["member_a"], ctx["project_a"])
                assert ei.value.status_code == 404
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F. Soft deletion isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_deleted_project_inaccessible_to_owner():
    from app.api.projects import _get_project_for_user
    from app.models.project import Project

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                project = await session.get(Project, ctx["project_a"])
                project.deleted_at = datetime.now(timezone.utc)
                await session.flush()
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                assert ei.value.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_soft_deleted_asset_excluded_from_list_query():
    from app.api.projects import _get_project_for_user
    from app.models.project import Asset

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                asset = await session.get(Asset, ctx["asset_a"])
                asset.deleted_at = datetime.now(timezone.utc)
                await session.flush()
                await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                rows = (
                    await session.execute(
                        select(Asset).where(
                            Asset.project_id == ctx["project_a"],
                            Asset.deleted_at.is_(None),
                        )
                    )
                ).scalars().all()
                assert ctx["asset_a"] not in {a.id for a in rows}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_soft_deleted_asset_content_guard():
    """Mirrors assets_upload.download_asset_content membership + deleted_at checks."""
    from app.api.projects import _get_project_for_user
    from app.models.project import Asset

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                asset = await session.get(Asset, ctx["asset_a"])
                asset.deleted_at = datetime.now(timezone.utc)
                await session.flush()
                asset = await session.get(Asset, ctx["asset_a"])
                assert asset is not None
                assert asset.project_id == ctx["project_a"]
                assert asset.deleted_at is not None
                missing = asset is None or asset.project_id != ctx["project_a"] or asset.deleted_at is not None
                assert missing is True
    finally:
        await engine.dispose()
