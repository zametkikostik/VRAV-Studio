"""Jobs API — probe + render + media intelligence enqueue (non-blocking)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path as P

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Job, Project
from app.models.timeline import Timeline, TimelineTrack
from app.schemas.project import JobOut
from app.services.media import ffmpeg_available, probe
from app.services.render import export_path_for_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ProbeJobRequest(BaseModel):
    organization_id: str
    project_id: str
    asset_id: str


class RenderTimelineRequest(BaseModel):
    organization_id: str
    project_id: str
    timeline_id: str | None = None
    clips: list[dict]
    width: int = Field(default=1280, ge=16, le=3840)
    height: int = Field(default=720, ge=16, le=2160)
    fps: float = Field(default=30.0, gt=0, le=60)


class RenderFromTimelineRequest(BaseModel):
    organization_id: str
    project_id: str
    timeline_id: str
    width: int = Field(default=1280, ge=16, le=3840)
    height: int = Field(default=720, ge=16, le=2160)
    fps: float = Field(default=30.0, gt=0, le=60)


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        project_id=str(job.project_id) if job.project_id else None,
        type=job.type,
        status=job.status,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
    )


async def _require_member(db: DbSession, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")


async def _asset_for_org_project(
    db: DbSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Asset:
    """Authorize membership + project ownership + asset belongs to project."""
    await _require_member(db, org_id, user_id)
    project = await db.get(Project, project_id)
    if project is None or project.organization_id != org_id or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


class AnalyzeAssetRequest(BaseModel):
    organization_id: str
    project_id: str
    asset_id: str
    extract_frames: bool = True


class TranscribeAssetRequest(BaseModel):
    organization_id: str
    project_id: str
    asset_id: str


@router.post("/probe", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def enqueue_probe(body: ProbeJobRequest, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
        asset_id = uuid.UUID(body.asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    await _require_member(db, org_id, user.id)
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    job = Job(
        id=uuid.uuid4(),
        organization_id=org_id,
        project_id=project_id,
        type="media.probe",
        status="pending",
        payload={"asset_id": str(asset_id), "storage_key": asset.storage_key},
    )
    db.add(job)
    await db.flush()
    try:
        from worker.celery_app import celery_app  # type: ignore

        async_result = celery_app.send_task("vrav.media.probe", args=[asset.storage_key])
        job.celery_task_id = async_result.id
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
    except Exception:
        path = P(os.getenv("LOCAL_STORAGE_PATH", "./data/storage")) / asset.storage_key
        try:
            job.result = probe(path)
            job.status = "succeeded"
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
        job.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return _job_out(job)


@router.post("/analyze", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def enqueue_analyze(body: AnalyzeAssetRequest, user: CurrentUser, db: DbSession):
    """Enqueue Celery media.analyze — never run FFmpeg in-request."""
    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
        asset_id = uuid.UUID(body.asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    await _asset_for_org_project(
        db, org_id=org_id, project_id=project_id, asset_id=asset_id, user_id=user.id
    )
    job = Job(
        id=uuid.uuid4(),
        organization_id=org_id,
        project_id=project_id,
        type="media.analyze",
        status="queued",
        payload={
            "asset_id": str(asset_id),
            "extract_frames": bool(body.extract_frames),
        },
    )
    db.add(job)
    await db.flush()
    try:
        from worker.celery_app import celery_app  # type: ignore

        async_result = celery_app.send_task(
            "vrav.media.analyze",
            args=[str(asset_id)],
            kwargs={"extract_frames": bool(body.extract_frames)},
        )
        job.celery_task_id = async_result.id
        job.status = "running"
        await db.flush()
    except Exception as e:
        job.status = "failed"
        job.error = f"enqueue failed: {type(e).__name__}"
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
    return _job_out(job)


@router.post("/transcribe", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def enqueue_transcribe(body: TranscribeAssetRequest, user: CurrentUser, db: DbSession):
    """Enqueue Celery media.transcribe — provider selection is server-side."""
    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
        asset_id = uuid.UUID(body.asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    await _asset_for_org_project(
        db, org_id=org_id, project_id=project_id, asset_id=asset_id, user_id=user.id
    )
    job = Job(
        id=uuid.uuid4(),
        organization_id=org_id,
        project_id=project_id,
        type="media.transcribe",
        status="queued",
        payload={"asset_id": str(asset_id)},
    )
    db.add(job)
    await db.flush()
    try:
        from worker.celery_app import celery_app  # type: ignore

        async_result = celery_app.send_task("vrav.media.transcribe", args=[str(asset_id)])
        job.celery_task_id = async_result.id
        job.status = "running"
        await db.flush()
    except Exception as e:
        job.status = "failed"
        job.error = f"enqueue failed: {type(e).__name__}"
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
    return _job_out(job)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession):
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await _require_member(db, job.organization_id, user.id)
    if job.status == "running" and job.celery_task_id:
        from app.api.jobs_celery_sync import sync_celery_job

        job = await sync_celery_job(job, db)
    return _job_out(job)


@router.post("/render", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def enqueue_render(body: RenderTimelineRequest, user: CurrentUser, db: DbSession):
    """Enqueue Celery media.render only — never block on FFmpeg or result.get()."""
    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    await _require_member(db, org_id, user.id)
    project = await db.get(Project, project_id)
    if project is None or project.organization_id != org_id or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not body.clips:
        raise HTTPException(status_code=400, detail="clips required")
    if len(body.clips) > 200:
        raise HTTPException(status_code=400, detail="too many clips (max 200)")
    if not ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not available")

    from app.services.credits import CreditService, InsufficientCreditsError

    try:
        await CreditService(db).reserve(
            org_id,
            Decimal("1.0000"),
            idempotency_key=f"render:{user.id}:{uuid.uuid4()}",
        )
    except InsufficientCreditsError as e:
        raise HTTPException(status_code=402, detail=str(e))

    job = Job(
        id=uuid.uuid4(),
        organization_id=org_id,
        project_id=project_id,
        type="media.render",
        status="running",
        payload={
            "timeline_id": body.timeline_id,
            "clips": body.clips,
            "width": body.width,
            "height": body.height,
            "fps": body.fps,
        },
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    storage_root = P(os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
    celery_clips = []
    for item in body.clips:
        try:
            aid = uuid.UUID(str(item["asset_id"]))
        except (KeyError, ValueError):
            job.status = "failed"
            job.error = "invalid asset_id in clips"
            job.finished_at = datetime.now(timezone.utc)
            await db.flush()
            raise HTTPException(status_code=400, detail="invalid asset_id in clips")
        asset = await db.get(Asset, aid)
        if asset is None or asset.project_id != project_id:
            job.status = "failed"
            job.error = f"asset not found: {aid}"
            job.finished_at = datetime.now(timezone.utc)
            await db.flush()
            raise HTTPException(status_code=404, detail=f"asset not found: {aid}")
        celery_clips.append(
            {
                "storage_key": asset.storage_key,
                "duration_ms": item.get("duration_ms"),
                "source_in_ms": int(item.get("source_in_ms") or 0),
            }
        )

    out = export_path_for_job(storage_root, str(org_id), str(project_id), str(job.id))
    rel_key = str(out.relative_to(storage_root)) if out.is_relative_to(storage_root) else str(out)

    try:
        from worker.celery_app import celery_app  # type: ignore

        async_result = celery_app.send_task(
            "vrav.media.render",
            kwargs={
                "clips": celery_clips,
                "output_key": rel_key,
                "storage_root": str(storage_root),
                "width": body.width,
                "height": body.height,
                "fps": body.fps,
            },
        )
        job.celery_task_id = async_result.id
        job.status = "running"
        job.result = {"output_key": rel_key, "queued": True}
        await db.flush()
        return _job_out(job)
    except Exception as e:
        job.status = "failed"
        job.error = f"celery_unavailable: {type(e).__name__}"
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=503, detail="Render worker unavailable")


@router.post("/render/timeline", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def render_from_timeline(body: RenderFromTimelineRequest, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
        timeline_id = uuid.UUID(body.timeline_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    await _require_member(db, org_id, user.id)
    result = await db.execute(
        select(Timeline)
        .options(selectinload(Timeline.tracks).selectinload(TimelineTrack.clips))
        .where(Timeline.id == timeline_id, Timeline.project_id == project_id)
    )
    timeline = result.scalar_one_or_none()
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    clip_payload: list[dict] = []
    for tr in sorted(timeline.tracks or [], key=lambda x: x.order_index):
        if tr.track_type != "video":
            continue
        for c in sorted(tr.clips or [], key=lambda x: x.start_ms):
            if not c.asset_id:
                continue
            clip_payload.append(
                {
                    "asset_id": str(c.asset_id),
                    "duration_ms": int(c.duration_ms),
                    "source_in_ms": 0,
                }
            )
    if not clip_payload:
        raise HTTPException(status_code=400, detail="No video clips on timeline")
    return await enqueue_render(
        RenderTimelineRequest(
            organization_id=str(org_id),
            project_id=str(project_id),
            timeline_id=str(timeline_id),
            clips=clip_payload,
            width=body.width,
            height=body.height,
            fps=body.fps,
        ),
        user,
        db,
    )


@router.get("/{job_id}/export")
async def download_export(job_id: uuid.UUID, user: CurrentUser, db: DbSession):
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await _require_member(db, job.organization_id, user.id)
    if job.type != "media.render" or job.status != "succeeded" or not job.result:
        raise HTTPException(status_code=400, detail="Export not available")
    key = (job.result or {}).get("output_key")
    if not key:
        raise HTTPException(status_code=404, detail="Output key missing")
    path = P(os.getenv("LOCAL_STORAGE_PATH", "./data/storage")) / str(key).lstrip("/")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file missing")
    return FileResponse(path, media_type="video/mp4", filename=f"export-{job_id}.mp4")
