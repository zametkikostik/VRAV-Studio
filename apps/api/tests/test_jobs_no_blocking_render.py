"""P0.5 — API must not block on Celery get or inline FFmpeg."""
from pathlib import Path


def test_jobs_render_does_not_block_on_celery_get():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "jobs.py").read_text()
    assert "async_result.get" not in text
    assert "Render worker unavailable" in text or "celery_unavailable" in text
    assert text.count("render_timeline(") == 0
