#!/usr/bin/env python3
"""API-level HTTP smoke E2E against live FastAPI + PostgreSQL (no browser).

Requires DATABASE_URL (postgresql+asyncpg) and migrated schema.
Uses ASGI transport — no network listen required.

Route prefixes match app.main (no global /api prefix):
  POST /auth/register, GET /health, POST /organizations, POST /projects
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
sys.path.insert(0, str(ROOT / "packages" / "ai-gateway"))
sys.path.insert(0, str(ROOT / "packages" / "core"))

os.environ.setdefault("SECRET_KEY", "ci-e2e-http-secret-key-32chars!!")
os.environ.setdefault("ENVIRONMENT", "development")


async def main() -> int:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        print("SKIP: DATABASE_URL not postgresql — HTTP E2E not run")
        return 0

    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.services.billing_grant import grant_paid_order_credits, load_order_for_update
    from app.models.billing import Order
    from app.db.session import AsyncSessionLocal
    import uuid as uuid_mod
    from app.models.user import User
    from app.models.organization import Organization, OrganizationMember
    from app.core.security import hash_password

    app = create_app()
    transport = ASGITransport(app=app)
    email = f"e2e_{uuid.uuid4().hex[:10]}@example.com"
    password = "E2ETestPass123!"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/auth/register",
            json={"email": email, "password": password, "full_name": "E2E User"},
        )
        if r.status_code not in (200, 201):
            print("REGISTER_FAIL", r.status_code, r.text[:300])
            return 1
        tokens = r.json()
        token = tokens.get("access_token") or tokens.get("access")
        assert token, tokens
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get("/health")
        print("health", r.status_code)

        r = await client.post(
            "/organizations",
            headers=headers,
            json={"name": "E2E Org", "slug": f"e2e-{uuid.uuid4().hex[:8]}"}
        )
        print("org", r.status_code, r.text[:200])
        org_id = None
        if r.status_code in (200, 201):
            org = r.json()
            org_id = org.get("id") or org.get("organization_id")
            if org_id:
                r = await client.post(
                    "/projects",
                    headers=headers,
                    json={"name": "E2E Project", "organization_id": org_id},
                )
                print("project", r.status_code, r.text[:200])

    async with AsyncSessionLocal() as session:
        uid = uuid_mod.uuid4()
        oid = uuid_mod.uuid4()
        order_id = uuid_mod.uuid4()
        session.add(
            User(
                id=uid,
                email=f"bill_{uid.hex[:8]}@ex.com",
                password_hash=hash_password("x"),
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            Organization(id=oid, name="Bill", slug=f"bill-{uid.hex[:6]}", owner_user_id=uid)
        )
        await session.flush()
        session.add(OrganizationMember(organization_id=oid, user_id=uid, role="owner"))
        session.add(
            Order(
                id=order_id,
                organization_id=oid,
                amount=Decimal("10.0000"),
                currency="USD",
                status="pending",
                plan_id="credits_100",
                credits_to_grant=Decimal("100.0000"),
                pricing_kind="credits",
                provider="stripe",
                snapshot={
                    "credits_to_grant": "100.0000",
                    "amount": "10.0000",
                    "currency": "USD",
                },
            )
        )
        await session.flush()
        order = await load_order_for_update(session, order_id)
        reason, granted = await grant_paid_order_credits(
            session,
            order=order,
            provider="stripe",
            provider_payment_id=f"pi_e2e_{order_id.hex[:10]}",
            event_id=f"evt_e2e_{order_id.hex[:8]}",
            raw_response={},
        )
        await session.commit()
        print("billing_grant", reason, granted)
        if reason != "granted" or granted != "100.0000":
            return 1

    print("HTTP_E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
