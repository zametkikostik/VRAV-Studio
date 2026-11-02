"""Asset transcript + embedding for AI analysis / RAG.

Revision ID: 012
Revises: 011

embedding stored as JSONB float array (len 1536 recommended).
Production may add pgvector index later without changing API contract.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column(
        "assets",
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assets", "embedding")
    op.drop_column("assets", "transcript")
