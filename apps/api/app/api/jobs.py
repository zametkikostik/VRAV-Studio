import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Job
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
        from pathlib import Path
        import os

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
