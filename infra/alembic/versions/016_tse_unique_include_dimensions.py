"""Include embedding_dimensions in transcript segment uniqueness.

Revision ID: 016
Revises: 015

Phase B.2: vector-space identity must be
asset_id + segment_index + provider + model + dimensions.
Migration 015 omitted dimensions, which could cause unique violations
when dimensions change for the same provider/model.

Downgrade policy (B.2.1):
If multiple rows share the old 4-column key with different dimensions,
downgrade aborts with a clear error and does not delete data.
"""
from alembic import op
import sqlalchemy as sa

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
    op.drop_index("ix_tse_project_space", table_name=TABLE)
    op.create_index(
        "ix_tse_project_space",
        TABLE,
        ["project_id", "embedding_provider", "embedding_model", "embedding_dimensions"],
    )


def downgrade() -> None:
    """Restore 015 uniqueness only when data is compatible.

    Multiple vector spaces (different embedding_dimensions) under the same
    (asset_id, segment_index, provider, model) cannot fit the old unique key.
    We refuse to drop data; operators must collapse or delete conflicting rows.
    """
    conn = op.get_bind()
    conflicts = conn.execute(
        sa.text(
            f"""
            SELECT asset_id::text, segment_index, embedding_provider, embedding_model,
                   COUNT(*) AS n, array_agg(DISTINCT embedding_dimensions) AS dims
            FROM {TABLE}
            GROUP BY asset_id, segment_index, embedding_provider, embedding_model
            HAVING COUNT(*) > 1
            LIMIT 10
            """
        )
    ).fetchall()
    if conflicts:
        sample = "; ".join(
            f"asset={r[0]} seg={r[1]} provider={r[2]} model={r[3]} count={r[4]} dims={r[5]}"
            for r in conflicts
        )
        raise RuntimeError(
            "Cannot downgrade migration 016 → 015: multiple vector-space rows would "
            "violate the restored unique constraint "
            "(asset_id, segment_index, embedding_provider, embedding_model). "
            "Collapse or delete alternate-dimension rows first, then retry. "
            f"Conflicts (sample): {sample}"
        )

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
