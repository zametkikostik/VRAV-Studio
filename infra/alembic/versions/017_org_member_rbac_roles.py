"""Normalize organization_members.role and enforce valid RBAC roles.

Revision ID: 017
Revises: 016
Create Date: 2026-11-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE organization_members m SET role = 'owner'
        FROM organizations o
        WHERE m.organization_id = o.id AND m.user_id = o.owner_user_id AND o.deleted_at IS NULL
    """)
    op.execute("""
        UPDATE organization_members SET role = lower(trim(role)) WHERE role IS NOT NULL
    """)
    op.execute("""
        UPDATE organization_members m SET role = 'admin'
        FROM organizations o
        WHERE m.organization_id = o.id AND lower(trim(m.role)) = 'owner'
          AND m.user_id <> o.owner_user_id AND o.deleted_at IS NULL
    """)
    op.execute("""
        UPDATE organization_members SET role = 'viewer'
        WHERE role IS NULL OR role NOT IN ('owner', 'admin', 'editor', 'viewer')
    """)
    op.create_check_constraint(
        "ck_organization_members_role", "organization_members",
        "role IN ('owner', 'admin', 'editor', 'viewer')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organization_members_role", "organization_members", type_="check")
