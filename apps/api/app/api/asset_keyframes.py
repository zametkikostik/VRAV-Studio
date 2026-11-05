"""Authenticated keyframe image serving (local storage only for now)."""
from __future__ import annotations

import os
import re
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Project
from app.services.media import resolve_storage_path

router = APIRouter(tags=["assets"])


async def _project_for_user(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(
            Project.id == project_id,
            OrganizationMember.user_id == user_id,
            Project.deleted_at.is_(None),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/assets/{asset_id}/keyframes/{filename}")
async def get_asset_keyframe(
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbSession,
):
    if not re.fullmatch(r"kf_\d{3}\.jpg", filename):
        raise HTTPException(status_code=400, detail="Invalid keyframe name")

    backend = (os.getenv("STORAGE_BACKEND") or "local").lower()
    if backend not in ("local", "fs", "filesystem", ""):
        raise HTTPException(
            status_code=501,
            detail="Keyframe serving is not available for this storage backend (DEFERRED)",
        )

    await _project_for_user(db, user.id, project_id)
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    meta = asset.metadata_ or {}
    kfs = meta.get("keyframes") if isinstance(meta, dict) else None
    if not isinstance(kfs, list) or not any(
        isinstance(k, dict) and k.get("filename") == filename for k in kfs
    ):
        raise HTTPException(status_code=404, detail="Keyframe not found")
    try:
        path = resolve_storage_path(asset.storage_key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid storage key")
    frame_path = (path.parent / f".kf_{asset.id.hex[:12]}" / filename).resolve()
    if not frame_path.is_relative_to(path.parent.resolve()) or not frame_path.exists():
        raise HTTPException(status_code=404, detail="Keyframe file missing")
    return Response(
        content=frame_path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
