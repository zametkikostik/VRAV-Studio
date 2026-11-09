"""Phase C.2.3.1 — PostgreSQL multi-tenant authorization matrix.

Requires DATABASE_URL (asyncpg → real PostgreSQL). Never mocked sessions.
Derives expected permissions from the actual implementation:

* `_get_project_for_user` / `_require_org_member` check membership existence only.
* OrganizationMember.role is stored but NOT evaluated on project/asset routes.
* Therefore owner and non-owner members share the same project read/write/delete
  gates; outsiders are denied (HTTP 404 / 403 depending on helper).
* Soft-deleted projects (deleted_at set) are inaccessible via `_get_project_for_user`.
* Soft-deleted assets are excluded from list_assets SQL and content download guards.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL not set — C.2.3.1 multi-tenant PG auth DEFERRED (INFRA SCOPE)",
    ),
]


async def _engine_session():
    from tests.phase_b21_pg_helpers import engine_session

    return await engine_session()


async def _seed_two_tenants(session):
    """Seed org A (owner + editor member) and org B (separate owner).

    Returns a dict of identities and resource IDs for assertions.
    """
    from app.core.security import hash_password
    from app.models.organization import Organization, OrganizationMember
    from app.models.project import Asset, Project
    from app.models.user import User

    owner_a = uuid.uuid4()
    member_a = uuid.uuid4()
    outsider = uuid.uuid4()
    owner_b = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    asset_a = uuid.uuid4()
    asset_b = uuid.uuid4()

    users = [
        (owner_a, "owner_a"),
        (member_a, "member_a"),
        (outsider, "outsider"),
        (owner_b, "owner_b"),
    ]
    for uid, label in users:
        session.add(
            User(
                id=uid,
                email=f"c231_{label}_{uid.hex[:8]}@example.com",
                password_hash=hash_password("TestPass123!"),
                full_name=label,
                is_active=True,
            )
        )
    await session.flush()

    session.add(Organization(id=org_a, name="Org A", slug=f"c231-a-{org_a.hex[:8]}", owner_user_id=owner_a))
    session.add(Organization(id=org_b, name="Org B", slug=f"c231-b-{org_b.hex[:8]}", owner_user_id=owner_b))
    await session.flush()

    # Owner + explicit non-owner member on org A
    session.add(OrganizationMember(organization_id=org_a, user_id=owner_a, role="owner"))
    session.add(OrganizationMember(organization_id=org_a, user_id=member_a, role="editor"))
    session.add(OrganizationMember(organization_id=org_b, user_id=owner_b, role="owner"))
    await session.flush()

    session.add(
        Project(
            id=project_a,
            organization_id=org_a,
            name="Project A",
            description=None,
            status="draft",
            created_by=owner_a,
        )
    )
    session.add(
        Project(
            id=project_b,
            organization_id=org_b,
            name="Project B",
            description=None,
            status="draft",
            created_by=owner_b,
        )
    )
    await session.flush()

    session.add(
        Asset(
            id=asset_a,
            project_id=project_a,
            type="video",
            storage_key=f"local/{asset_a.hex}/a.mp4",
            filename="a.mp4",
            mime_type="video/mp4",
            size_bytes=100,
            metadata_={},
        )
    )
    session.add(
        Asset(
            id=asset_b,
            project_id=project_b,
            type="video",
            storage_key=f"local/{asset_b.hex}/b.mp4",
            filename="b.mp4",
            mime_type="video/mp4",
            size_bytes=200,
            metadata_={},
        )
    )
    await session.flush()

    return {
        "owner_a": owner_a,
        "member_a": member_a,
        "outsider": outsider,
        "owner_b": owner_b,
        "org_a": org_a,
        "org_b": org_b,
        "project_a": project_a,
        "project_b": project_b,
        "asset_a": asset_a,
        "asset_b": asset_b,
    }
