"""Celery job status mapping tests (no Redis)."""
from datetime import datetime, timezone
from types import SimpleNamespace


def apply_payload(job, payload):
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
    return job


def test_render_payload_ok():
    job = SimpleNamespace(status="running", result=None, error=None, finished_at=None)
    apply_payload(job, {"ok": True, "output_key": "a.mp4", "size_bytes": 100, "duration_sec": 2.0})
    assert job.status == "succeeded"
    assert job.result["celery"] is True
    assert job.finished_at is not None


def test_render_payload_fail():
    job = SimpleNamespace(status="running", result=None, error=None, finished_at=None)
    apply_payload(job, {"ok": False, "error": "boom"})
    assert job.status == "failed"
    assert "boom" in job.error
