from types import SimpleNamespace
from app.services.job_progress import job_progress_payload


def test_progress_queued():
    p = job_progress_payload(SimpleNamespace(id="j1", status="queued", error=None, type="ai.generate"))
    assert p["status"] == "queued" and p["progress"] == 10


def test_progress_running():
    p = job_progress_payload(SimpleNamespace(id="j1", status="running", error=None, type="media.render"))
    assert p["status"] == "processing"


def test_progress_succeeded_has_export():
    p = job_progress_payload(SimpleNamespace(id="abc", status="succeeded", error=None, type="media.render"))
    assert p["status"] == "completed" and p["output_url"] == "/jobs/abc/export"


def test_progress_failed():
    p = job_progress_payload(SimpleNamespace(id="j1", status="failed", error="boom", type="media.render"))
    assert p["status"] == "failed" and p["error"] == "boom"
