"""Include embedding_dimensions in transcript segment uniqueness.

Revision ID: 016
Revises: 015

Phase B.2: vector-space identity must be
asset_id + segment_index + provider + model + dimensions.
Migration 015 omitted dimensions, which could cause unique violations
when dimensions change for the same provider/model.
"""
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

OLD_UQ = "uq_tse_asset_seg_space"
NEW_UQ = "uq_tse_asset_seg_vector_space"
TABLE = "transcript_segment_embeddings"


def upgrade() -> None:
    op.drop_constraint(OLD_UQ, TABLE, type_="unique")
    op.create_unique_constraint(
        NEW_UQ,
        TABLE,
        [
            "asset_id",
            "segment_index",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
        ],
    )
    # Broaden project space index to include dimensions for query planning
    op.drop_index("ix_tse_project_space", table_name=TABLE)
    op.create_index(
        "ix_tse_project_space",
        TABLE,
        ["project_id", "embedding_provider", "embedding_model", "embedding_dimensions"],
    )


def downgrade() -> None:
    op.drop_index("ix_tse_project_space", table_name=TABLE)
    op.create_index(
        "ix_tse_project_space",
        TABLE,
        ["project_id", "embedding_provider", "embedding_model"],
    )
    op.drop_constraint(NEW_UQ, TABLE, type_="unique")
    op.create_unique_constraint(
        OLD_UQ,
        TABLE,
        [
            "asset_id",
            "segment_index",
            "embedding_provider",
            "embedding_model",
        ],
    )
