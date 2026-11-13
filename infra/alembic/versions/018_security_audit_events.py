"""Durable security audit events for organization membership lifecycle.

Revision ID: 018
Revises: 017
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("previous_role", sa.String(32), nullable=True),
        sa.Column("new_role", sa.String(32), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_security_audit_events_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_security_audit_events_organization_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_security_audit_events_org_created",
        "security_audit_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_security_audit_events_actor_created",
        "security_audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_security_audit_events_event_created",
        "security_audit_events",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_audit_events_event_created", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_actor_created", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_org_created", table_name="security_audit_events")
    op.drop_table("security_audit_events")
