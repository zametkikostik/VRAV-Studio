"""Transcript segment embeddings for Semantic Video Search Phase B.

Revision ID: 015
Revises: 014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_segment_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding_provider", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("start_ms >= 0", name="ck_tse_start_ms_nonneg"),
        sa.CheckConstraint("end_ms >= start_ms", name="ck_tse_end_ge_start"),
        sa.UniqueConstraint("asset_id", "segment_index", "embedding_provider", "embedding_model", name="uq_tse_asset_seg_space"),
    )
    op.create_index("ix_tse_project_id", "transcript_segment_embeddings", ["project_id"])
    op.create_index("ix_tse_asset_id", "transcript_segment_embeddings", ["asset_id"])
    op.create_index(
        "ix_tse_project_space",
        "transcript_segment_embeddings",
        ["project_id", "embedding_provider", "embedding_model"],
    )


def downgrade() -> None:
    op.drop_index("ix_tse_project_space", table_name="transcript_segment_embeddings")
    op.drop_index("ix_tse_asset_id", table_name="transcript_segment_embeddings")
    op.drop_index("ix_tse_project_id", table_name="transcript_segment_embeddings")
    op.drop_table("transcript_segment_embeddings")
