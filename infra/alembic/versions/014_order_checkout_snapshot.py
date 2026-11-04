"""Immutable checkout snapshot fields on orders.

Revision ID: 014
Revises: 013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("plan_id", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("credits_to_grant", sa.Numeric(19, 4), nullable=True))
    op.add_column("orders", sa.Column("pricing_kind", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column(
        "orders",
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "snapshot")
    op.drop_column("orders", "provider")
    op.drop_column("orders", "pricing_kind")
    op.drop_column("orders", "credits_to_grant")
    op.drop_column("orders", "plan_id")
