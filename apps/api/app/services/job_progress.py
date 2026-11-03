"""Map Job ORM/status fields → UI progress payload for WS/HTTP clients."""
from __future__ import annotations

from typing import Any


def job_progress_payload(job: Any) -> dict[str, Any]:
    status = (getattr(job, "status", None) or "pending").lower()
    if status in ("pending", "queued"):
        ui_status, progress, message = "queued", 10, "Waiting for worker"
    elif status == "running":
        ui_status, progress, message = "processing", 55, "Rendering / processing"
    elif status == "succeeded":
        ui_status, progress, message = "completed", 100, "Completed"
    elif status in ("failed", "cancelled", "canceled"):
        ui_status, progress, message = "failed", 100, getattr(job, "error", None) or "Failed"
    else:
        ui_status, progress, message = "queued", 5, status

    job_id = str(getattr(job, "id", ""))
    out: dict[str, Any] = {
        "job_id": job_id,
        "status": ui_status,
        "progress": progress,
        "message": message,
        "backend_status": status,
        "type": getattr(job, "type", None),
    }
    err = getattr(job, "error", None)
    if err:
        out["error"] = err
    if status == "succeeded" and job_id:
        out["output_url"] = f"/jobs/{job_id}/export"
    return out
