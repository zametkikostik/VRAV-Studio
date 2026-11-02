"""AI agent: prompt → RAG → plan → compile → render."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Job, Project
from app.schemas.ai_agent import GenerateRequest, GenerateResponse
from app.services.ai_agent import AgentError, generate_video_from_prompt

router = APIRouter(tags=["ai-agent"])


async def _get_project(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
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
    "/projects/{project_id}/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_video(
    project_id: str,
    body: GenerateRequest,
    user: CurrentUser,
    db: DbSession,
):
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")

    project = await _get_project(db, user.id, pid)
    result = await db.execute(
        select(Asset).where(Asset.project_id == pid, Asset.deleted_at.is_(None))
    )
    rows = result.scalars().all()
    assets = [
        {
            "id": str(a.id),
            "type": a.type,
            "filename": a.filename,
            "storage_key": a.storage_key,
            "embedding": a.embedding,
            "transcript": a.transcript,
        }
        for a in rows
    ]
    storage_root = Path(os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
    asset_paths = {str(a.id): (storage_root / a.storage_key) for a in rows if a.storage_key}

    job_id = uuid.uuid4()
    try:
        out = await generate_video_from_prompt(
            project_id=str(project.id),
            organization_id=str(project.organization_id),
            prompt=body.prompt,
            assets=assets,
            asset_paths=asset_paths,
            storage_root=storage_root,
            top_k=body.top_k,
            model=body.model,
            job_id=str(job_id),
        )
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    job = Job(
        id=job_id,
        organization_id=project.organization_id,
        project_id=project.id,
        type="ai.generate",
        status="queued" if out.get("status") == "queued" else out.get("status") or "queued",
        payload={
            "prompt": body.prompt,
            "selected_asset_ids": out.get("selected_asset_ids"),
            "plan_source": out.get("plan_source"),
            "output_key": out.get("output_key"),
        },
        result={"timeline": out.get("timeline")},
        celery_task_id=out.get("celery_task_id"),
        started_at=datetime.now(timezone.utc),
    )
    if out.get("celery_task_id"):
        job.status = "running"
    db.add(job)
    await db.flush()

    return GenerateResponse(
        job_id=str(job.id),
        status=job.status,
        timeline=out.get("timeline"),
        selected_asset_ids=out.get("selected_asset_ids") or [],
        plan_source=out.get("plan_source"),
    )
