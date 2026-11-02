"""Add api_request_logs table

Revision ID: 013
Revises: 012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("query_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("request_id", sa.String(50), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_api_logs_user_id", "api_request_logs", ["user_id"])
    op.create_index("ix_api_logs_organization_id", "api_request_logs", ["organization_id"])
    op.create_index("ix_api_logs_created_at", "api_request_logs", ["created_at"])
    op.create_index("ix_api_logs_path", "api_request_logs", ["path"])
    op.create_index("ix_api_logs_request_id", "api_request_logs", ["request_id"])
    op.create_index("ix_api_logs_user_created", "api_request_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_logs_user_created", table_name="api_request_logs")
    op.drop_index("ix_api_logs_request_id", table_name="api_request_logs")
    op.drop_index("ix_api_logs_path", table_name="api_request_logs")
    op.drop_index("ix_api_logs_created_at", table_name="api_request_logs")
    op.drop_index("ix_api_logs_organization_id", table_name="api_request_logs")
    op.drop_index("ix_api_logs_user_id", table_name="api_request_logs")
    op.drop_table("api_request_logs")
