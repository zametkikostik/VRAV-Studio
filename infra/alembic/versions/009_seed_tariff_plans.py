"""Seed default tariff plans for server-side pricing.

Revision ID: 009
Revises: 008
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision: Union[str, None] = "008"
branch_labels = None
depends_on = None

PLANS = [
    {
        "id": "credits_100",
        "name": "100 Credits",
        "description": "One-time credit pack",
        "price_monthly": "10.0000",
        "currency": "USD",
        "included_credits": "100.0000",
        "features": '{"kind": "credits"}',
    },
    {
        "id": "credits_500",
        "name": "500 Credits",
        "description": "One-time credit pack",
        "price_monthly": "40.0000",
        "currency": "USD",
        "included_credits": "500.0000",
        "features": '{"kind": "credits"}',
    },
    {
        "id": "pro_monthly",
        "name": "Pro Monthly",
        "description": "Pro subscription with monthly credits",
        "price_monthly": "29.0000",
        "currency": "USD",
        "included_credits": "300.0000",
        "features": '{"kind": "subscription"}',
    },
    {
        "id": "selfhosted",
        "name": "Self-hosted License",
        "description": "Self-hosted deployment license",
        "price_monthly": "199.0000",
        "currency": "USD",
        "included_credits": "0.0000",
        "features": '{"kind": "license"}',
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for p in PLANS:
        conn.execute(
            sa.text(
                """
                INSERT INTO tariff_plans (id, name, description, price_monthly, currency, included_credits, features, is_active)
                VALUES (:id, :name, :description, :price_monthly, :currency, :included_credits, CAST(:features AS jsonb), true)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    price_monthly = EXCLUDED.price_monthly,
                    currency = EXCLUDED.currency,
                    included_credits = EXCLUDED.included_credits,
                    features = EXCLUDED.features,
                    is_active = true
                """
            ),
            p,
        )


def downgrade() -> None:
    conn = op.get_bind()
    for p in PLANS:
        conn.execute(sa.text("DELETE FROM tariff_plans WHERE id = :id"), {"id": p["id"]})
