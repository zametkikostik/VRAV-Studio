"""Multipart asset upload endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Project
from app.schemas.asset_serializers import asset_to_out
from app.schemas.project import AssetOut
from app.services.storage import get_storage

router = APIRouter(tags=["assets"])
ALLOWED_TYPES = {"image", "video", "audio", "model", "other"}


async def _project_for_user(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(Project.id == project_id, OrganizationMember.user_id == user_id, Project.deleted_at.is_(None))
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/projects/{project_id}/assets/upload", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    asset_type: str = Form("other"),
    scene_id: str | None = Form(None),
):
    from app.core.config import get_settings

    project = await _project_for_user(db, user.id, project_id)
    if asset_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"asset_type must be one of {sorted(ALLOWED_TYPES)}")
    settings = get_settings()
    max_bytes = settings.max_upload_bytes
    filename = file.filename or "upload.bin"
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds max upload size of {max_bytes} bytes"
        )
    storage = get_storage()
    key = storage.make_key(str(project.organization_id), str(project.id), filename)
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
    return asset_to_out(asset)


@router.get("/projects/{project_id}/assets/{asset_id}/content")
async def download_asset_content(
    project_id: uuid.UUID, asset_id: uuid.UUID, user: CurrentUser, db: DbSession
):
    from fastapi.responses import Response

    await _project_for_user(db, user.id, project_id)
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    storage = get_storage()
    try:
        data = await storage.get(asset.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Object missing in storage")
    safe_name = "".join(c for c in (asset.filename or "asset") if c.isalnum() or c in "._- ")[:128] or "asset"
    is_svg = (asset.mime_type or "").startswith("image/svg")
    disp = ("attachment" if is_svg else "inline") + f'; filename="{safe_name}"'
    return Response(
        content=data,
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": disp,
            "Cache-Control": "private, max-age=60",
        },
    )
