from app.services.rag_search import EMBEDDING_DIM, deterministic_embed, rank_assets_by_embedding


def test_embed_dim():
    v = deterministic_embed("hello")
    assert len(v) == EMBEDDING_DIM


def test_search_orders():
    q_text = "unique-query-token-xyz"
    assets = [
        {"id": "1", "embedding": deterministic_embed(q_text)},
        {"id": "2", "embedding": deterministic_embed("completely-different-zzz")},
    ]
    hits = rank_assets_by_embedding(deterministic_embed(q_text), assets, top_k=2, min_score=-1.0)
    assert hits[0].asset_id == "1"
    assert hits[0].score > hits[1].score
