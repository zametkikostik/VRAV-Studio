"""One succeeded payment per order (double-grant protection).

Revision ID: 010
Revises: 009
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_order_succeeded
        ON payments (order_id)
        WHERE status = 'succeeded'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_payment_order_succeeded")
