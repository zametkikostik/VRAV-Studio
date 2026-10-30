"""billing tables

Revision ID: 004
Revises: 003
Create Date: 2026-10-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tariff_plans",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_monthly", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("included_credits", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("features", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("plan_id", sa.String(50), sa.ForeignKey("tariff_plans.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_subscription_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_payment_id", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"),
    )

    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("provider_refund_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_webhook_provider_event"),
    )

    op.create_table(
        "credit_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, unique=True),
        sa.Column("balance", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("balance >= 0", name="ck_credit_balance_nonneg"),
        sa.CheckConstraint("reserved >= 0", name="ck_credit_reserved_nonneg"),
    )

    op.create_table(
        "credit_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_reservations_account_id", "credit_reservations", ["account_id"])

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id"), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credit_reservations.id"), nullable=True),
        sa.Column("entry_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(19, 4), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_ledger_account_id", "credit_ledger", ["account_id"])

    op.execute(
        """
        INSERT INTO tariff_plans (id, name, description, price_monthly, currency, included_credits, features, is_active)
        VALUES
        ('free', 'Free', 'Starter', 0, 'USD', 100, '{"ai_chat": true}', true),
        ('pro', 'Pro', 'Professional', 29.0000, 'USD', 5000, '{"ai_chat": true, "export_hd": true}', true),
        ('studio', 'Studio', 'Team', 99.0000, 'USD', 25000, '{"ai_chat": true, "export_hd": true, "white_label": true}', true)
        """
    )


def downgrade() -> None:
    op.drop_table("credit_ledger")
    op.drop_table("credit_reservations")
    op.drop_table("credit_accounts")
    op.drop_table("webhook_events")
    op.drop_table("refunds")
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("subscriptions")
    op.drop_table("tariff_plans")
