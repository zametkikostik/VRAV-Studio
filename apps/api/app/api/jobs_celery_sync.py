"""Sync running jobs from Celery AsyncResult (optional Redis)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.project import Job


async def sync_celery_job(job: Job, db) -> Job:
    """If job is running with celery_task_id, pull AsyncResult once (non-blocking)."""
    if job.status != "running" or not job.celery_task_id:
        return job
    try:
        from celery.result import AsyncResult
        from worker.celery_app import celery_app  # type: ignore

        ar = AsyncResult(job.celery_task_id, app=celery_app)
        if not ar.ready():
            return job
        if ar.failed():
            job.status = "failed"
            job.error = str(ar.result)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return job
        payload = ar.result
        if job.type == "media.render" and isinstance(payload, dict):
            if payload.get("ok"):
                job.status = "succeeded"
                job.result = {
                    "output_key": payload.get("output_key"),
                    "size_bytes": payload.get("size_bytes"),
                    "duration_sec": payload.get("duration_sec"),
                    "celery": True,
                }
                job.finished_at = datetime.now(timezone.utc)
            else:
                job.status = "failed"
                job.error = str(payload.get("error") or "render failed")[:2000]
                job.result = payload
                job.finished_at = datetime.now(timezone.utc)
            await db.flush()
        elif job.type == "media.probe" and isinstance(payload, dict):
            if payload.get("error"):
                job.status = "failed"
                job.error = str(payload["error"])[:2000]
            else:
                job.status = "succeeded"
                job.result = payload
            job.finished_at = datetime.now(timezone.utc)
            await db.flush()
    except Exception:
        pass
    return job
