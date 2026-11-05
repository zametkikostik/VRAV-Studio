"""Iteration 13: keyframe timestamps, transcription provider gate, job sync semantics."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.media import sample_keyframe_timestamps_ms
from app.services.transcription import (
    TranscriptionUnavailableError,
    get_transcription_provider,
    validate_transcript_payload,
)
from app.api.jobs_celery_sync import _payload_failed, sync_celery_job


def test_sample_keyframes_30fps_long():
    ts = sample_keyframe_timestamps_ms(60_000, 6)
    assert len(ts) == 6
    assert ts[0] > 0
    assert ts[-1] < 60_000
    assert ts == sorted(ts)
    assert len(set(ts)) == 6


def test_sample_keyframes_short_and_single():
    assert sample_keyframe_timestamps_ms(500, 1) == [250]
    assert sample_keyframe_timestamps_ms(0, 5) == []
    assert sample_keyframe_timestamps_ms(10_000, 0) == []


def test_sample_respects_max_frames_cap():
    ts = sample_keyframe_timestamps_ms(3_600_000, 100)
    assert len(ts) <= 24


def test_validate_transcript_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_transcript_payload({"text": "  ", "segments": []})


def test_validate_transcript_rejects_bad_timestamps():
    with pytest.raises(ValueError):
        validate_transcript_payload(
            {"text": "hi", "segments": [{"start_ms": 10, "end_ms": 5, "text": "x"}]}
        )


def test_mock_provider_only_when_explicit(monkeypatch):
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(TranscriptionUnavailableError):
        get_transcription_provider()
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "mock")
    p = get_transcription_provider()
    assert p is not None


def test_mock_transcribe_when_test_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    p = get_transcription_provider()
    import asyncio

    out = asyncio.run(p.transcribe(audio_path="/tmp/x"))
    assert out["provider"] == "mock"
    validated = validate_transcript_payload(out)
    assert validated["text"]


def test_payload_failed_detects_error_dict():
    assert _payload_failed({"error": "boom"})
    assert _payload_failed({"ok": False, "error": "x"})
    assert _payload_failed({"status": "unavailable", "error": "no provider"})
    assert _payload_failed({"ok": True}) is None
    assert _payload_failed({"probe": {}}) is None


def test_sync_marks_failed_on_error_payload():
    job = SimpleNamespace(
        status="running",
        celery_task_id="tid",
        type="media.analyze",
        error=None,
        result=None,
        finished_at=None,
    )
    db = AsyncMock()
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
    sys.modules["celery.result"] = celery_result
    sys.modules["worker"] = worker_mod
    sys.modules["worker.celery_app"] = worker_celery
    import asyncio

    out = asyncio.run(sync_celery_job(job, db))
    assert out.status == "failed"
    assert "escapes" in (out.error or "")


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
