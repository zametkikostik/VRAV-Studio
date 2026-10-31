"""Reference P0.5 enqueue-only render block (applied in jobs.py)."""
# after export_path_for_job(...):
#
# try:
#     from worker.celery_app import celery_app
#     async_result = celery_app.send_task("vrav.media.render", kwargs={...})
#     job.celery_task_id = async_result.id
#     job.status = "running"
#     job.result = {"output_key": rel_key, "queued": True}
#     await db.flush()
#     return JobOut(...)
# except Exception as e:
#     job.status = "failed"
#     job.error = f"celery_unavailable: {type(e).__name__}"
#     job.finished_at = datetime.now(timezone.utc)
#     await db.flush()
#     raise HTTPException(status_code=503, detail="Render worker unavailable")
#
# FORBIDDEN in HTTP handler:
#   async_result.get(...)
#   render_timeline(...)
