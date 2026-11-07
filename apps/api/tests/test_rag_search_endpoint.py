"""RAG search ranking smoke tests (no DB)."""
from __future__ import annotations

from app.services.rag_search import (
    deterministic_embed,
    filter_assets_for_embedding_space,
    search_by_text,
    search_by_text_sync_mock,
)


def test_search_by_text_ranks_matching_asset():
    q = "relocation bulgaria"
    emb = deterministic_embed(q)
    assets = [
        {
            "id": "1",
            "filename": "a.mp4",
            "type": "video",
            "embedding": emb,
            "transcript": "moving to Bulgaria",
        },
        {
            "id": "2",
            "filename": "b.mp4",
            "type": "video",
            "embedding": deterministic_embed("unrelated cooking"),
            "transcript": None,
        },
    ]
    hits = search_by_text_sync_mock(q, assets, top_k=2)
    assert hits
    assert hits[0].asset_id == "1"
    assert hits[0].score >= hits[1].score


def test_search_by_text_uses_mock_provider(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    q = "relocation bulgaria"
    assets = [
        {
            "id": "1",
            "filename": "a.mp4",
            "type": "video",
            "embedding": deterministic_embed(q),
            "transcript": "moving to Bulgaria",
        },
        {
            "id": "2",
            "filename": "b.mp4",
            "type": "video",
            "embedding": deterministic_embed("unrelated cooking"),
            "transcript": None,
        },
    ]
    hits = search_by_text(q, assets, top_k=2)
    assert hits[0].asset_id == "1"


def test_openai_space_excludes_untagged_legacy_vectors():
    """Legacy hash embeddings without provider/model tags must not enter OpenAI space."""
    assets = [
        {
            "id": "legacy",
            "embedding": deterministic_embed("hello"),
            "filename": "old.mp4",
        },
        {
            "id": "openai-ready",
            "embedding": [0.01] * 1536,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 1536,
            "filename": "new.mp4",
        },
        {
            "id": "model-only",
            "embedding": [0.01] * 1536,
            "embedding_model": "text-embedding-3-small",
            "filename": "partial.mp4",
        },
    ]
    compat = filter_assets_for_embedding_space(
        assets,
        provider_name="openai",
        model="text-embedding-3-small",
        dimensions=1536,
    )
    assert [a["id"] for a in compat] == ["openai-ready"]


def test_openai_space_rejects_wrong_provider_model_dimensions():
    good = {
        "id": "ok",
        "embedding": [0.01] * 1536,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
    }
    wrong_provider = {**good, "id": "wp", "embedding_provider": "mock"}
    wrong_model = {**good, "id": "wm", "embedding_model": "text-embedding-3-large"}
    wrong_dim = {**good, "id": "wd", "embedding_dimensions": 768}
    prefix_collision = {
        **good,
        "id": "prefix",
        "embedding_model": "text-embedding-3-small-extra",
    }
    assets = [good, wrong_provider, wrong_model, wrong_dim, prefix_collision]
    compat = filter_assets_for_embedding_space(
        assets,
        provider_name="openai",
        model="text-embedding-3-small",
        dimensions=1536,
    )
    assert [a["id"] for a in compat] == ["ok"]


def test_mock_space_accepts_untagged_hash_vectors():
    assets = [{"id": "1", "embedding": deterministic_embed("x")}]
    compat = filter_assets_for_embedding_space(
        assets, provider_name="mock", model="deterministic-hash"
    )
    assert len(compat) == 1
