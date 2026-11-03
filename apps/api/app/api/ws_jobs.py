"""WebSocket job progress stream — auth before accept; poll DB for status."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_access_token
from app.services.job_progress import job_progress_payload as _progress_payload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs-ws"])

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "canceled"})


async def _authorize_job(websocket: WebSocket, job_id: str) -> tuple[str, uuid.UUID] | None:
    from app.db.session import AsyncSessionLocal
    from app.models.organization import OrganizationMember
    from app.models.project import Job

    token = websocket.query_params.get("token")
    if not token:
        auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    user_id = decode_access_token(token)
    if not user_id:
        return None
    try:
        job_uuid = uuid.UUID(job_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return None

    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_uuid)
            if job is None:
                return None
            mem = await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == job.organization_id,
                    OrganizationMember.user_id == user_uuid,
                )
            )
            if mem.scalar_one_or_none() is None:
                return None
        return user_id, job_uuid
    except Exception as e:
        logger.warning("ws job auth failed: %s", type(e).__name__)
        return None


@router.websocket("/ws/jobs/{job_id}/progress")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    auth = await _authorize_job(websocket, job_id)
    if auth is None:
        await websocket.close(code=4401)
        return
    _user_id, job_uuid = auth
    await websocket.accept()

    from app.db.session import AsyncSessionLocal
    from app.models.project import Job

    try:
        while True:
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, job_uuid)
                if job is None:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "job_id": job_id,
                                "status": "failed",
                                "progress": 100,
                                "error": "Job not found",
                            }
                        )
                    )
                    break
                if job.status == "running" and job.celery_task_id:
                    try:
                        from app.api.jobs_celery_sync import sync_celery_job

                        job = await sync_celery_job(job, db)
                    except Exception:
                        pass
                payload = _progress_payload(job)
                await websocket.send_text(json.dumps(payload, ensure_ascii=False))
                if (job.status or "").lower() in TERMINAL:
                    break
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws job progress error: %s", type(e).__name__)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
