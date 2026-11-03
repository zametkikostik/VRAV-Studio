"""RAG search ranking smoke tests (no DB)."""
from app.services.rag_search import deterministic_embed, search_by_text


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
    hits = search_by_text(q, assets, top_k=2)
    assert hits
    assert hits[0].asset_id == "1"
    assert hits[0].score >= hits[1].score
