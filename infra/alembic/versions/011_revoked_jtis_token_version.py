"""Revoked JTIs and user token_version for session invalidation.

Revision ID: 011
Revises: 010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_jtis",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_revoked_jtis_user_id", "revoked_jtis", ["user_id"])
    op.create_index("ix_revoked_jtis_expires_at", "revoked_jtis", ["expires_at"])
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_index("ix_revoked_jtis_expires_at", table_name="revoked_jtis")
    op.drop_index("ix_revoked_jtis_user_id", table_name="revoked_jtis")
    op.drop_table("revoked_jtis")
