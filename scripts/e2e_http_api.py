#!/usr/bin/env python3
"""API-level HTTP smoke E2E (ASGI). Asserts status codes; billing via webhook HTTP + fixtures.

Requires DATABASE_URL postgresql+asyncpg and migrated schema.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
    from app.db.session import AsyncSessionLocal
    from app.models.billing import Order, Payment, CreditAccount
    from app.services.payment import WebhookResult
    from sqlalchemy import select

    app = create_app()
    transport = ASGITransport(app=app)
    email = f"e2e_{uuid.uuid4().hex[:10]}@example.com"
    password = "E2ETestPass123!"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/auth/register",
            json={"email": email, "password": password, "full_name": "E2E User"},
        )
        assert r.status_code in (200, 201), f"register {r.status_code} {r.text[:300]}"
        tokens = r.json()
        token = tokens.get("access_token")
        assert token, tokens
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get("/health")
        assert r.status_code == 200, f"health {r.status_code}"

        slug = f"e2e-{uuid.uuid4().hex[:8]}"
        r = await client.post(
            "/organizations",
            headers=headers,
            json={"name": "E2E Org", "slug": slug},
        )
        assert r.status_code in (200, 201), f"org {r.status_code} {r.text[:300]}"
        org = r.json()
        org_id = org.get("id") or org.get("organization_id")
        assert org_id, org

        r = await client.post(
            "/projects",
            headers=headers,
            json={"name": "E2E Project", "organization_id": org_id},
        )
        assert r.status_code in (200, 201), f"project {r.status_code} {r.text[:300]}"

        order_id = uuid.uuid4()
        async with AsyncSessionLocal() as session:
            oid = uuid.UUID(str(org_id))
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
            await session.commit()

        event_id = f"evt_e2e_{order_id.hex[:12]}"
        payment_id = f"pi_e2e_{order_id.hex[:12]}"
        stripe_payload = {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": payment_id,
                    "payment_status": "paid",
                    "amount_total": 1000,
                    "currency": "usd",
                    "metadata": {"order_id": str(order_id), "plan_id": "credits_100"},
                }
            },
        }
        mock_result = WebhookResult(
            event_type="checkout.session.completed",
            payment_id=payment_id,
            status="paid",
            raw=stripe_payload,
        )

        with patch("app.api.billing_checkout.get_stripe") as gs:
            provider = AsyncMock()
            provider.handle_webhook = AsyncMock(return_value=mock_result)
            gs.return_value = provider
            r = await client.post(
                "/billing/webhooks/stripe",
                content=json.dumps(stripe_payload).encode(),
                headers={"stripe-signature": "t=1,v1=test"},
            )
        assert r.status_code == 200, f"stripe webhook {r.status_code} {r.text[:400]}"
        body = r.json()
        assert body.get("status") == "processed", body
        assert body.get("credits_granted") == "100.0000", body

        with patch("app.api.billing_checkout.get_stripe") as gs:
            provider = AsyncMock()
            provider.handle_webhook = AsyncMock(return_value=mock_result)
            gs.return_value = provider
            r2 = await client.post(
                "/billing/webhooks/stripe",
                content=json.dumps(stripe_payload).encode(),
                headers={"stripe-signature": "t=1,v1=test"},
            )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("status") == "already_processed", r2.json()

        async with AsyncSessionLocal() as session:
            pays = (
                await session.execute(
                    select(Payment).where(Payment.order_id == order_id, Payment.status == "succeeded")
                )
            ).scalars().all()
            assert len(pays) == 1
            order = await session.get(Order, order_id)
            assert order is not None and order.status == "paid"
            acc = (
                await session.execute(
                    select(CreditAccount).where(CreditAccount.organization_id == oid)
                )
            ).scalar_one_or_none()
            assert acc is not None and acc.balance == Decimal("100.0000")

    print("HTTP_E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
