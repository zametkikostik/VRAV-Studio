import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Job, Project
from app.schemas.project import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ProbeJobRequest(BaseModel):
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

    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")

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
        import os
        from pathlib import Path

        from app.services.media import probe

        path = Path(os.getenv("LOCAL_STORAGE_PATH", "./data/storage")) / asset.storage_key
        try:
            result = probe(path)
            job.status = "succeeded"
            job.result = result
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
        job.finished_at = datetime.now(timezone.utc)

    await db.flush()
    return JobOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        project_id=str(job.project_id) if job.project_id else None,
        type=job.type,
        status=job.status,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession):
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == job.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")
    return JobOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        project_id=str(job.project_id) if job.project_id else None,
        type=job.type,
        status=job.status,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
    )


class RenderTimelineRequest(BaseModel):
    organization_id: str
    project_id: str
    timeline_id: str | None = None
    clips: list[dict]
    width: int = 1280
    height: int = 720
    fps: float = 30.0


@router.post("/render", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def enqueue_render(body: RenderTimelineRequest, user: CurrentUser, db: DbSession):
    import os
    from pathlib import Path as P

    from app.services.media import ffmpeg_available
    from app.services.render import RenderClip, RenderRequest, export_path_for_job, render_timeline

    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")

    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")

    project = await db.get(Project, project_id)
    if project is None or project.organization_id != org_id or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not body.clips:
        raise HTTPException(status_code=400, detail="clips required")

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

    if not ffmpeg_available():
        job.status = "failed"
        job.error = "ffmpeg not available"
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=503, detail="ffmpeg not available")

    storage_root = P(os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
    render_clips: list[RenderClip] = []
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
        path = storage_root / asset.storage_key.lstrip("/")
        render_clips.append(
            RenderClip(
                path=path,
                duration_ms=item.get("duration_ms"),
                source_in_ms=int(item.get("source_in_ms") or 0),
            )
        )

    out = export_path_for_job(storage_root, str(org_id), str(project_id), str(job.id))

    # Prefer Celery when broker is reachable
    try:
        from worker.celery_app import celery_app  # type: ignore

        celery_clips = []
        for item in body.clips:
            asset = await db.get(Asset, uuid.UUID(str(item["asset_id"])))
            celery_clips.append(
                {
                    "storage_key": asset.storage_key,
                    "duration_ms": item.get("duration_ms"),
                    "source_in_ms": int(item.get("source_in_ms") or 0),
                }
            )
        rel_key = str(out.relative_to(storage_root)) if out.is_relative_to(storage_root) else str(out)
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
        await db.flush()
        try:
            payload = async_result.get(timeout=2)
            if isinstance(payload, dict) and payload.get("ok"):
                job.status = "succeeded"
                job.result = {
                    "output_key": rel_key,
                    "size_bytes": payload.get("size_bytes"),
                    "duration_sec": payload.get("duration_sec"),
                    "celery": True,
                }
                job.finished_at = datetime.now(timezone.utc)
                await db.flush()
                return JobOut(
                    id=str(job.id),
                    organization_id=str(job.organization_id),
                    project_id=str(job.project_id) if job.project_id else None,
                    type=job.type,
                    status=job.status,
                    error=job.error,
                    created_at=job.created_at.isoformat() if job.created_at else None,
                )
        except Exception:
            await db.flush()
            return JobOut(
                id=str(job.id),
                organization_id=str(job.organization_id),
                project_id=str(job.project_id) if job.project_id else None,
                type=job.type,
                status=job.status,
                error=job.error,
                created_at=job.created_at.isoformat() if job.created_at else None,
            )
    except Exception:
        pass  # inline fallback

    try:
        result = render_timeline(
            RenderRequest(
                clips=render_clips,
                output_path=out,
                width=body.width,
                height=body.height,
                fps=body.fps,
            )
        )
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=500, detail=str(e))

    if not result.ok:
        job.status = "failed"
        job.error = result.error or "render failed"
        job.result = {"log_tail": result.log_tail}
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=500, detail=job.error)

    rel_key = str(out.relative_to(storage_root)) if out.is_relative_to(storage_root) else str(out)
    job.status = "succeeded"
    job.result = {
        "output_key": rel_key,
        "size_bytes": result.size_bytes,
        "duration_sec": result.duration_sec,
        "probe": {
            "format": (result.probe.get("format") or {}).get("format_name"),
            "duration": (result.probe.get("format") or {}).get("duration"),
        },
    }
    job.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return JobOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        project_id=str(job.project_id) if job.project_id else None,
        type=job.type,
        status=job.status,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
    )


class RenderFromTimelineRequest(BaseModel):
    organization_id: str
    project_id: str
    timeline_id: str
    width: int = 1280
    height: int = 720
    fps: float = 30.0


@router.post("/render/timeline", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def render_from_timeline(body: RenderFromTimelineRequest, user: CurrentUser, db: DbSession):
    from sqlalchemy.orm import selectinload

    from app.models.timeline import Timeline, TimelineTrack

    try:
        org_id = uuid.UUID(body.organization_id)
        project_id = uuid.UUID(body.project_id)
        timeline_id = uuid.UUID(body.timeline_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")

    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")

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

    fake = RenderTimelineRequest(
        organization_id=str(org_id),
        project_id=str(project_id),
        timeline_id=str(timeline_id),
        clips=clip_payload,
        width=body.width,
        height=body.height,
        fps=body.fps,
    )
    return await enqueue_render(fake, user, db)


@router.get("/{job_id}/export")
async def download_export(job_id: uuid.UUID, user: CurrentUser, db: DbSession):
    import os
    from pathlib import Path as P

    from fastapi.responses import FileResponse

    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    mem = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == job.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")
    if job.type != "media.render" or job.status != "succeeded" or not job.result:
        raise HTTPException(status_code=400, detail="Export not available")
    key = (job.result or {}).get("output_key")
    if not key:
        raise HTTPException(status_code=404, detail="Output key missing")
    root = P(os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
    path = root / str(key).lstrip("/")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file missing")
    return FileResponse(path, media_type="video/mp4", filename=f"export-{job_id}.mp4")
