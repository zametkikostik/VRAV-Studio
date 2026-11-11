"""Multipart asset upload with bounded memory (spooled temp file) and lifecycle cleanup."""
from __future__ import annotations

import logging
import tempfile
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models.project import Asset, Scene
from app.schemas.asset_serializers import asset_to_out
from app.schemas.project import AssetOut
from app.services.storage import get_storage
from app.services.upload_policy import ALLOWED_ASSET_TYPES, ALLOWED_MIME_PREFIXES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["assets"])

_SPOOL_MAX_MEM = 1 * 1024 * 1024


async def _project_for_upload(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID):
    """Asset upload requires asset:write (editor+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.ASSET_WRITE)


async def _project_for_download(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID):
    """Asset download requires asset:read (viewer+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.ASSET_READ)


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
    if asset_type not in ALLOWED_ASSET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid asset_type: {asset_type}. Allowed: {sorted(ALLOWED_ASSET_TYPES)}",
        )
    ct = (file.content_type or "application/octet-stream").lower()
    if not any(ct.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {ct}")

    project = await _project_for_upload(db, user.id, project_id)
    settings = get_settings()
    max_bytes = settings.max_upload_bytes

    sid: uuid.UUID | None = None
    if scene_id:
        try:
            sid = uuid.UUID(scene_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scene_id")
        scene = await db.get(Scene, sid)
        if scene is None or scene.project_id != project.id:
            raise HTTPException(status_code=400, detail="Scene not found in this project")

    storage = get_storage()
    filename = file.filename or "upload.bin"
    key = storage.make_key(str(project.organization_id), str(project.id), filename)

    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_MEM)
    total = 0
    stored = False
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds max upload size of {max_bytes} bytes",
                )
            spool.write(chunk)
        spool.seek(0)
        meta = await storage.put(key, spool, content_type=file.content_type)
        stored = True
        pending = db.info.setdefault("pending_storage_keys", [])
        pending.append(key)

        asset = Asset(
            id=uuid.uuid4(),
            project_id=project_id,
            scene_id=sid,
            type=asset_type,
            storage_key=key,
            filename=filename,
            mime_type=file.content_type,
            size_bytes=total,
            metadata_=meta if isinstance(meta, dict) else None,
        )
        db.add(asset)
        await db.flush()
        return asset_to_out(asset)
    except Exception:
        if stored:
            try:
                await storage.delete(key)
            except Exception:
                logger.exception("failed to cleanup storage key %s", key)
        raise
    finally:
        spool.close()


@router.get("/projects/{project_id}/assets/{asset_id}/content")
async def download_asset_content(
    project_id: uuid.UUID, asset_id: uuid.UUID, user: CurrentUser, db: DbSession
):
    from fastapi.responses import Response

    await _project_for_download(db, user.id, project_id)
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    storage = get_storage()
    try:
        data = await storage.get(asset.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Object missing in storage")
    safe_name = "".join(c for c in (asset.filename or "asset") if c.isalnum() or c in "._- ")[:128] or "asset"
    is_svg = (asset.mime_type or "").startswith("image/svg")
    disp = ("attachment" if is_svg else "inline") + f"; filename=\"{safe_name}\""
    return Response(
        content=data,
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": disp,
            "Cache-Control": "private, max-age=60",
        },
    )
