"""RAG search readiness notes (JSONB embeddings remain source of truth).

Revision ID: 013
Revises: 012

Native pgvector index is optional ops work:
  CREATE EXTENSION IF NOT EXISTS vector;
  -- then dual-write/backfill a vector(1536) column if desired.
This migration only records a no-op schema stamp so deploy pipelines
apply a clear revision boundary for Iteration 5.
"""
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT 1")


def downgrade() -> None:
    pass
