"""Sync running jobs from Celery AsyncResult (optional Redis)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.project import Job


def _payload_failed(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("error"):
        return str(payload["error"])[:2000]
    if payload.get("ok") is False:
        return str(payload.get("error") or "task failed")[:2000]
    status = payload.get("status")
    if status in ("unavailable", "transcript_segments_unavailable"):
        return str(payload.get("error") or status)[:2000]
    return None


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
        err = _payload_failed(payload)
        if job.type in (
            "media.render",
            "media.probe",
            "media.analyze",
            "media.transcribe",
            "media.index_segments",
        ):
            if err:
                job.status = "failed"
                job.error = err
                if isinstance(payload, dict):
                    safe = {k: v for k, v in payload.items() if k not in ("path", "probe")}
                    if "probe" in payload and isinstance(payload["probe"], dict):
                        safe["probe"] = {
                            kk: vv
                            for kk, vv in payload["probe"].items()
                            if kk != "path"
                        }
                    job.result = safe
                job.finished_at = datetime.now(timezone.utc)
            elif job.type == "media.render" and isinstance(payload, dict):
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
            elif isinstance(payload, dict):
                job.status = "succeeded"
                drop = {"path", "embedding", "embeddings", "vectors"}
                safe = {k: v for k, v in payload.items() if k not in drop}
                job.result = safe
                job.finished_at = datetime.now(timezone.utc)
            await db.flush()
    except Exception:
        pass
    return job
