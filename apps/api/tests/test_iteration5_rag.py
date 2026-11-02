"""Iteration 5: RAG search over asset embeddings."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.rag_search import (
    EMBEDDING_DIM,
    RagError,
    cosine_similarity,
    deterministic_embed,
    normalize_embedding,
    rank_assets_by_embedding,
    search_by_text,
)


def test_deterministic_embed_stable_and_normalized():
    a = deterministic_embed("hello world")
    b = deterministic_embed("hello world")
    assert a == b
    assert len(a) == EMBEDDING_DIM
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_deterministic_embed_rejects_empty():
    with pytest.raises(RagError):
        deterministic_embed("   ")


def test_cosine_identical_is_one():
    v = normalize_embedding([1.0, 0.0, 0.0] + [0.0] * (EMBEDDING_DIM - 3))
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_rank_prefers_matching_embedding():
    q = deterministic_embed("sunset beach waves")
    assets = [
        {"id": "1", "embedding": deterministic_embed("sunset beach waves"), "filename": "a.mp4"},
        {"id": "2", "embedding": deterministic_embed("completely different topic xyz"), "filename": "b.mp4"},
    ]
    hits = rank_assets_by_embedding(q, assets, top_k=2)
    assert hits[0].asset_id == "1"
    assert hits[0].score > hits[1].score


def test_search_by_text_top_k():
    assets = [
        {"id": "a", "embedding": deterministic_embed("cat video"), "type": "video"},
        {"id": "b", "embedding": deterministic_embed("dog video"), "type": "video"},
        {"id": "c", "embedding": deterministic_embed("space documentary"), "type": "video"},
    ]
    hits = search_by_text("cat", assets, top_k=1)
    assert len(hits) == 1
    assert hits[0].asset_id == "a"


def test_rag_api_module_exists():
    assert (Path(__file__).resolve().parents[1] / "app/api/rag.py").exists()
    assert (Path(__file__).resolve().parents[1] / "app/services/rag_search.py").exists()


def test_migration_013_exists():
    mig = Path(__file__).resolve().parents[3] / "infra/alembic/versions/013_rag_search_notes.py"
    assert mig.exists()
    assert 'down_revision = "012"' in mig.read_text()


def test_main_includes_rag_router():
    text = (Path(__file__).resolve().parents[1] / "app/main.py").read_text()
    assert "rag_router" in text
