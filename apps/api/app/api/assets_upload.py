"""Multipart asset upload endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Project
from app.schemas.project import AssetOut
from app.services.storage import get_storage

router = APIRouter(tags=["assets"])

ALLOWED_TYPES = {"image", "video", "audio", "model", "other"}


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/assets/upload",
    response_model=AssetOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    asset_type: str = Form("other"),
    scene_id: str | None = Form(None),
):
    if asset_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"asset_type must be one of {sorted(ALLOWED_TYPES)}")

    project = await _project_for_user(db, user.id, project_id)
    storage = get_storage()
    filename = file.filename or "upload.bin"
    key = storage.make_key(str(project.organization_id), str(project.id), filename)
    data = await file.read()
    meta = await storage.put(key, data, content_type=file.content_type)

    sid = None
    if scene_id:
        try:
            sid = uuid.UUID(scene_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scene_id")

    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        scene_id=sid,
        type=asset_type,
        storage_key=key,
        filename=filename,
        mime_type=file.content_type,
        size_bytes=meta.size,
    )
    db.add(asset)
    await db.flush()
    return AssetOut(
        id=str(asset.id),
        project_id=str(asset.project_id),
        scene_id=str(asset.scene_id) if asset.scene_id else None,
        type=asset.type,
        storage_key=asset.storage_key,
        filename=asset.filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
    )
