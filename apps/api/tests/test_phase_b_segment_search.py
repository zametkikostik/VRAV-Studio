"""Phase B: strict vectors, segment index helpers, space identity."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.rag_search import (
    RagError,
    filter_assets_for_embedding_space,
    require_embedding_vector,
    vector_space_id,
)
from app.services.segment_index import (
    TranscriptSegmentsUnavailable,
    extract_segments_from_asset,
    _content_hash,
)


def test_require_vector_exact_dim():
    v = [0.1] * 8
    assert len(require_embedding_vector(v, expected_dim=8)) == 8


def test_require_vector_rejects_short():
    with pytest.raises(RagError, match="dimension"):
        require_embedding_vector([0.1, 0.2], expected_dim=8)


def test_require_vector_rejects_long():
    with pytest.raises(RagError, match="dimension"):
        require_embedding_vector([0.1] * 10, expected_dim=8)


def test_require_vector_rejects_nan():
    v = [0.0] * 4
    v[1] = float("nan")
    with pytest.raises(RagError, match="non-finite"):
        require_embedding_vector(v, expected_dim=4)


def test_require_vector_rejects_inf():
    v = [0.0] * 4
    v[2] = float("inf")
    with pytest.raises(RagError, match="non-finite"):
        require_embedding_vector(v, expected_dim=4)


def test_require_vector_rejects_empty():
    with pytest.raises(RagError, match="empty"):
        require_embedding_vector([], expected_dim=4)


def test_vector_space_id_exact():
    a = vector_space_id(provider="openai", model="text-embedding-3-small", dimensions=1536)
    b = vector_space_id(provider="openai", model="text-embedding-3-small", dimensions=1536)
    c = vector_space_id(provider="openai", model="text-embedding-3-large", dimensions=1536)
    assert a == b
    assert a != c


def test_openai_space_excludes_untagged_and_prefix_match():
    assets = [
        {"id": "1", "embedding": [0.1] * 4},
        {
            "id": "2",
            "embedding": [0.1] * 4,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 4,
        },
        {
            "id": "3",
            "embedding": [0.1] * 4,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small-ft",
            "embedding_dimensions": 4,
        },
    ]
    compat = filter_assets_for_embedding_space(
        assets, provider_name="openai", model="text-embedding-3-small", dimensions=4
    )
    assert [a["id"] for a in compat] == ["2"]


def test_extract_segments_preserves_timestamps():
    class A:
        metadata_ = {
            "transcription": {
                "segments": [
                    {"start_ms": 1200, "end_ms": 3400, "text": "hello world"},
                    {"start_ms": 5000, "end_ms": 7000, "text": "pricing"},
                ]
            }
        }

    segs = extract_segments_from_asset(A())  # type: ignore
    assert segs[0].start_ms == 1200 and segs[0].end_ms == 3400
    assert segs[1].text == "pricing"


def test_extract_segments_unavailable():
    class A:
        metadata_ = {}

    with pytest.raises(TranscriptSegmentsUnavailable):
        extract_segments_from_asset(A())  # type: ignore


def test_content_hash_stable():
    assert _content_hash(1, 2, "a") == _content_hash(1, 2, "a")
    assert _content_hash(1, 2, "a") != _content_hash(1, 2, "b")


def test_index_segments_job_and_worker_registered():
    """Application wiring for Phase B indexing must be present."""
    jobs = Path(__file__).resolve().parents[1] / "app/api/jobs.py"
    worker = Path(__file__).resolve().parents[2] / "worker" / "worker" / "tasks.py"
    jt = jobs.read_text()
    wt = worker.read_text()
    assert "media.index_segments" in jt
    assert "/index-segments" in jt
    assert 'name="vrav.media.index_segments"' in wt
    assert "index_asset_segments" in wt


def test_search_api_prefers_segments_and_index_not_ready():
    src = (Path(__file__).resolve().parents[1] / "app/api/projects.py").read_text()
    assert "search_project_segments" in src
    assert "index_not_ready" in src
