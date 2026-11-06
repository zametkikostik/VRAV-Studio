"""Iteration 13 — media intelligence job API + Celery lifecycle (unit)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def test_mock_transcription_provider_explicit():
    from app.services.transcription import get_transcription_provider

    p = get_transcription_provider("mock")
    out = asyncio.run(p.transcribe(audio_path="/tmp/x.wav"))
    assert out["text"]
    assert out["provider"] == "mock"
    assert out["segments"]


def test_transcription_unavailable_without_provider(monkeypatch):
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    from app.services.transcription import TranscriptionUnavailableError, get_transcription_provider

    with pytest.raises(TranscriptionUnavailableError):
        get_transcription_provider()


def test_transcription_test_env_allows_mock(monkeypatch):
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    from app.services.transcription import get_transcription_provider

    p = get_transcription_provider()
    assert p.__class__.__name__ == "MockTranscriptionProvider"


def test_empty_transcript_rejected():
    from app.services.transcription import validate_transcript_payload

    with pytest.raises(ValueError):
        validate_transcript_payload({"text": "", "segments": []})


def test_invalid_segment_timestamps_rejected():
    from app.services.transcription import validate_transcript_payload

    with pytest.raises(ValueError):
        validate_transcript_payload(
            {
                "text": "x",
                "segments": [{"start_ms": 100, "end_ms": 50, "text": "bad"}],
            }
        )


def test_sync_celery_job_marks_path_escape_failed():
    """Worker result with storage path escape fails the job without exposing keys."""
    from app.api.jobs_celery_sync import sync_celery_job

    job = SimpleNamespace(
        id=uuid4(),
        status="running",
        celery_task_id="tid-1",
        type="media.analyze",
        error=None,
        result=None,
        finished_at=None,
    )
    db = MagicMock()
    db.flush = AsyncMock()

    import sys
    from types import ModuleType

    celery_result = ModuleType("celery.result")

    class AsyncResult:
        def __init__(self, *a, **k):
            pass

        def ready(self):
            return True

        def failed(self):
            return False

        result = {"error": "path escapes storage root"}

    celery_result.AsyncResult = AsyncResult
    worker_mod = ModuleType("worker")
    worker_celery = ModuleType("worker.celery_app")
    worker_celery.celery_app = object()
    prev_celery_result = sys.modules.get("celery.result")
    prev_worker = sys.modules.get("worker")
    prev_worker_celery = sys.modules.get("worker.celery_app")
    sys.modules["celery.result"] = celery_result
    sys.modules["worker"] = worker_mod
    sys.modules["worker.celery_app"] = worker_celery
    import asyncio as _asyncio

    try:
        out = _asyncio.run(sync_celery_job(job, db))
        assert out.status == "failed"
        assert "escapes" in (out.error or "")
    finally:

        def _restore(name, prev):
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev

        _restore("celery.result", prev_celery_result)
        _restore("worker", prev_worker)
        _restore("worker.celery_app", prev_worker_celery)


def test_jobs_api_defines_analyze_transcribe_routes():
    text = open(
        __file__.replace("tests/test_iteration13_media_jobs.py", "app/api/jobs.py")
    ).read()
    assert '@router.post("/analyze"' in text
    assert '@router.post("/transcribe"' in text
    assert "vrav.media.analyze" in text
    assert "vrav.media.transcribe" in text
    assert "_asset_for_org_project" in text


def test_plan_context_still_enriched():
    from app.services.plan_generate import asset_row_to_context

    asset = SimpleNamespace(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        type="video",
        filename="a.mp4",
        transcript=None,
        mime_type="video/mp4",
        metadata_={
            "probe": {
                "status": "ok",
                "duration_ms": 5000,
                "video": {"width": 1280, "height": 720, "fps": 24.0, "codec": "h264"},
                "audio": {"codec": "aac"},
            },
            "keyframes": [{"index": 0, "timestamp_ms": 1000, "filename": "kf_000.jpg"}],
        },
    )
    ctx = asset_row_to_context(asset)
    assert ctx["duration_ms"] == 5000
    assert ctx["width"] == 1280
    assert ctx["fps"] == 24.0
    assert ctx["keyframes"][0]["timestamp_ms"] == 1000
