"""Organization-scoped RBAC policy (Phase C.2.4).

Roles: owner, admin, editor, viewer.
Permissions are enforced server-side from OrganizationMember.role in PostgreSQL.
Client-supplied role claims (JWT or request body) are never trusted.
"""
from __future__ import annotations

import logging
import uuid
from enum import StrEnum

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import OrganizationMember
from app.models.project import Project

logger = logging.getLogger("vrav.security.rbac")

VALID_ROLES = frozenset({"owner", "admin", "editor", "viewer"})


class Permission(StrEnum):
    PROJECT_READ = "project:read"
    PROJECT_CREATE = "project:create"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"
    ASSET_READ = "asset:read"
    ASSET_WRITE = "asset:write"
    ORG_MEMBERS_MANAGE = "org:members_manage"
    ORG_ASSIGN_EDITOR_VIEWER = "org:assign_editor_viewer"
    ORG_ASSIGN_ADMIN = "org:assign_admin"
    ORG_TRANSFER_OWNERSHIP = "org:transfer_ownership"
    ORG_DELETE = "org:delete"


_ROLE_PERMS: dict[str, frozenset[Permission]] = {
    "viewer": frozenset({Permission.PROJECT_READ, Permission.ASSET_READ}),
    "editor": frozenset({
        Permission.PROJECT_READ, Permission.PROJECT_CREATE, Permission.PROJECT_UPDATE,
        Permission.ASSET_READ, Permission.ASSET_WRITE,
    }),
    "admin": frozenset({
        Permission.PROJECT_READ, Permission.PROJECT_CREATE, Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE, Permission.ASSET_READ, Permission.ASSET_WRITE,
        Permission.ORG_MEMBERS_MANAGE, Permission.ORG_ASSIGN_EDITOR_VIEWER,
    }),
    "owner": frozenset(Permission),
}


def role_has(role: str, perm: Permission) -> bool:
    r = (role or "").lower().strip()
    return perm in _ROLE_PERMS.get(r, frozenset())


def normalize_role(raw: str | None) -> str:
    r = (raw or "").lower().strip()
    if r in VALID_ROLES:
        return r
    return "viewer"


async def get_membership(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> OrganizationMember | None:
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def require_org_permission(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID, perm: Permission) -> OrganizationMember:
    mem = await get_membership(db, user_id, org_id)
    if mem is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of organization")
    if not role_has(mem.role, perm):
        audit_security_event("rbac_denied_org", user_id=user_id, org_id=org_id, role=mem.role, permission=perm.value)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return mem


async def require_project_permission(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, perm: Permission) -> Project:
    result = await db.execute(
        select(Project, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(Project.id == project_id, OrganizationMember.user_id == user_id, Project.deleted_at.is_(None))
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project, mem = row
    if not role_has(mem.role, perm):
        audit_security_event("rbac_denied_project", user_id=user_id, project_id=project_id, role=mem.role, permission=perm.value)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return project


def assert_role_assignment_allowed(actor_role: str, target_role: str) -> None:
    actor = normalize_role(actor_role)
    target = normalize_role(target_role)
    if target == "owner":
        raise HTTPException(status_code=403, detail="Cannot assign owner via role update; use ownership transfer")
    if target == "admin":
        if actor != "owner":
            raise HTTPException(status_code=403, detail="Only owner can assign admin")
        return
    if target in ("editor", "viewer"):
        if actor not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Insufficient permissions to assign role")
        return
    raise HTTPException(status_code=400, detail="Invalid role")


def audit_security_event(event: str, **fields) -> None:
    logger.info("security_event:%s", event, extra={"security_event": event, **{k: str(v) for k, v in fields.items()}})
