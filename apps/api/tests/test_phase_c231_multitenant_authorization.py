"""Phase C.2.3.1 multi-tenant authorization matrix (readable PostgreSQL tests).

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
# A. Owner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_read_own_project():
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                project = await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                assert project.id == ctx["project_a"]
                assert project.organization_id == ctx["org_a"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_can_list_own_assets():
    from app.api.projects import _get_project_for_user
    from app.models.project import Asset

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                await _get_project_for_user(session, ctx["owner_a"], ctx["project_a"])
                result = await session.execute(
                    select(Asset).where(
                        Asset.project_id == ctx["project_a"],
                        Asset.deleted_at.is_(None),
                    )
                )
                assets = result.scalars().all()
                assert {a.id for a in assets} == {ctx["asset_a"]}
                assert all(a.project_id == ctx["project_a"] for a in assets)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_cannot_access_foreign_tenant_project():
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["owner_a"], ctx["project_b"])
                assert ei.value.status_code == 404
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# B. Non-owner member (role=editor)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_can_read_project_under_membership_contract():
    """Implementation does not distinguish role; any membership grants project read."""
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                project = await _get_project_for_user(session, ctx["member_a"], ctx["project_a"])
                assert project.id == ctx["project_a"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_member_can_perform_update_under_membership_contract():
    """update_project gates solely on _get_project_for_user — member may update."""
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                project = await _get_project_for_user(session, ctx["member_a"], ctx["project_a"])
                project.name = "Renamed by member"
                await session.flush()
                await session.refresh(project)
                assert project.name == "Renamed by member"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_member_cannot_access_unrelated_organization_project():
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["member_a"], ctx["project_b"])
                assert ei.value.status_code == 404
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# C. Outsider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outsider_project_read_denied():
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["outsider"], ctx["project_a"])
                assert ei.value.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_outsider_org_member_check_forbidden():
    from app.api.projects import _require_org_member

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                with pytest.raises(HTTPException) as ei:
                    await _require_org_member(session, ctx["outsider"], ctx["org_a"])
                assert ei.value.status_code == 403
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_outsider_cannot_mutate_project_name():
    """Outsider never obtains a Project row via auth gate; DB name must stay unchanged."""
    from app.api.projects import _get_project_for_user
    from app.models.project import Project

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                original = (await session.get(Project, ctx["project_a"])).name
                with pytest.raises(HTTPException):
                    await _get_project_for_user(session, ctx["outsider"], ctx["project_a"])
                # No mutation path reached
                await session.refresh(await session.get(Project, ctx["project_a"]))
                assert (await session.get(Project, ctx["project_a"])).name == original
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_outsider_cross_tenant_idor_with_valid_ids():
    from app.api.projects import _get_project_for_user

    engine, Session = await _engine_session()
    try:
        async with Session() as session:
            async with session.begin():
                ctx = await _seed_two_tenants(session)
                # Valid project_b id, outsider identity
                with pytest.raises(HTTPException) as ei:
                    await _get_project_for_user(session, ctx["outsider"], ctx["project_b"])
                assert ei.value.status_code == 404
    finally:
        await engine.dispose()
