"""P0.5 — jobs render should enqueue Celery media.render."""
from pathlib import Path


def test_jobs_render_enqueues_celery_task_name():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "jobs.py").read_text()
    assert "vrav.media.render" in text
