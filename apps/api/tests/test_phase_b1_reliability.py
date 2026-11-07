"""Phase B.1: job lifecycle, ASR enqueue validation, search contract."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.jobs_celery_sync import _payload_failed, sync_celery_job
from app.services.segment_index import (
    SegmentIndexError,
    TranscriptSegmentsUnavailable,
    extract_segments_from_asset,
)


def test_payload_failed_index_unavailable_statuses():
    assert _payload_failed({"status": "unavailable", "error": "no key"}) == "no key"
    assert (
        _payload_failed({"status": "transcript_segments_unavailable", "error": "no segs"})
        == "no segs"
    )
    assert _payload_failed({"ok": True, "segments_indexed": 3}) is None


def test_extract_requires_canonical_transcription_segments():
    class A:
        metadata_ = {"segments": [{"start_ms": 0, "end_ms": 1, "text": "x"}]}

    with pytest.raises(TranscriptSegmentsUnavailable):
        extract_segments_from_asset(A())

    class B:
        metadata_ = {}
        transcript = "full text without segments"

    with pytest.raises(TranscriptSegmentsUnavailable):
        extract_segments_from_asset(B())

    class C:
        metadata_ = {"transcription": {"segments": []}}

    with pytest.raises(TranscriptSegmentsUnavailable):
        extract_segments_from_asset(C())

    class D:
        metadata_ = {
            "transcription": {
                "segments": [{"start_ms": 10, "end_ms": 5, "text": "bad"}]
            }
        }

    with pytest.raises(SegmentIndexError, match="out-of-range|timestamp"):
        extract_segments_from_asset(D())

    class E:
        metadata_ = {
            "transcription": {
                "segments": [{"start_ms": 100, "end_ms": 200, "text": "hello"}]
            }
        }

    segs = extract_segments_from_asset(E())
    assert segs[0].start_ms == 100 and segs[0].end_ms == 200


@pytest.mark.asyncio
async def test_sync_index_segments_success():
    job = SimpleNamespace(
        status="running",
        celery_task_id="t1",
        type="media.index_segments",
        error=None,
        result=None,
        finished_at=None,
    )
    db = AsyncMock()
    db.flush = AsyncMock()

    class AR:
        def ready(self):
            return True

        def failed(self):
            return False

        result = {
            "ok": True,
            "segments_indexed": 2,
            "embedding_provider": "mock",
            "embedding_model": "deterministic-hash",
            "embedding_dimensions": 8,
            "vector_space": "mock::deterministic-hash::8",
        }

    with patch("celery.result.AsyncResult", return_value=AR()):
        with patch.dict("sys.modules", {"worker.celery_app": MagicMock()}):
            out = await sync_celery_job(job, db)
    assert out.status == "succeeded"
    assert out.result["segments_indexed"] == 2
    assert out.finished_at is not None


@pytest.mark.asyncio
async def test_sync_index_segments_provider_unavailable():
    job = SimpleNamespace(
        status="running",
        celery_task_id="t2",
        type="media.index_segments",
        error=None,
        result=None,
        finished_at=None,
    )
    db = AsyncMock()
    db.flush = AsyncMock()

    class AR:
        def ready(self):
            return True

        def failed(self):
            return False

        result = {"status": "unavailable", "error": "EMBEDDING_PROVIDER is not set"}

    with patch("celery.result.AsyncResult", return_value=AR()):
        with patch.dict("sys.modules", {"worker.celery_app": MagicMock()}):
            out = await sync_celery_job(job, db)
    assert out.status == "failed"
    assert "EMBEDDING_PROVIDER" in (out.error or "")
    assert out.finished_at is not None


@pytest.mark.asyncio
async def test_sync_index_segments_celery_exception():
    job = SimpleNamespace(
        status="running",
        celery_task_id="t3",
        type="media.index_segments",
        error=None,
        result=None,
        finished_at=None,
    )
    db = AsyncMock()
    db.flush = AsyncMock()

    class AR:
        def ready(self):
            return True

        def failed(self):
            return True

        result = RuntimeError("boom")

    with patch("celery.result.AsyncResult", return_value=AR()):
        with patch.dict("sys.modules", {"worker.celery_app": MagicMock()}):
            out = await sync_celery_job(job, db)
    assert out.status == "failed"
    assert out.finished_at is not None


@pytest.mark.asyncio
async def test_sync_skips_already_terminal():
    job = SimpleNamespace(
        status="succeeded",
        celery_task_id="t4",
        type="media.index_segments",
        error=None,
        result={"segments_indexed": 1},
        finished_at=datetime.now(timezone.utc),
    )
    db = AsyncMock()
    out = await sync_celery_job(job, db)
    assert out.status == "succeeded"
    db.flush.assert_not_called()


def test_jobs_enqueue_uses_canonical_extract():
    text = open(
        __file__.replace("tests/test_phase_b1_reliability.py", "app/api/jobs.py")
    ).read()
    assert "extract_segments_from_asset" in text
    assert "transcription.segments" in text
    assert 'meta.get("transcript_segments") or meta.get("segments")' not in text


def test_search_contract_no_silent_asset_fallback():
    text = open(
        __file__.replace("tests/test_phase_b1_reliability.py", "app/api/projects.py")
    ).read()
    assert "search_project_segments" in text
    assert "index_not_ready" in text
    assert "rank_assets_by_embedding" not in text


def test_celery_sync_lists_index_segments():
    text = open(
        __file__.replace(
            "tests/test_phase_b1_reliability.py", "app/api/jobs_celery_sync.py"
        )
    ).read()
    assert "media.index_segments" in text


def test_worker_registers_index_segments_task():
    from pathlib import Path

    worker = Path(__file__).resolve().parents[2] / "worker" / "worker" / "tasks.py"
    assert 'name="vrav.media.index_segments"' in worker.read_text()
