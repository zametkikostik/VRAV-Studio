"""RAG / semantic asset search over stored embeddings (JSONB float arrays)."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Sequence

EMBEDDING_DIM = 1536


class RagError(Exception):
    pass


def normalize_embedding(values: Sequence[float], *, dim: int = EMBEDDING_DIM) -> list[float]:
    if not values:
        raise RagError("empty embedding")
    vec = [float(x) for x in values]
    if len(vec) > dim:
        vec = vec[:dim]
    if len(vec) < dim:
        vec = vec + [0.0] * (dim - len(vec))
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        n = min(len(a), len(b))
        a = list(a)[:n]
        b = list(b)[:n]
    if not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def deterministic_embed(text: str, *, dim: int = EMBEDDING_DIM) -> list[float]:
    if not (text or "").strip():
        raise RagError("text is required for embedding")
    raw = (text or "").strip().encode("utf-8")
    seed = hashlib.sha256(raw).digest()
    values: list[float] = []
    block = seed
    while len(values) < dim:
        block = hashlib.sha256(block + raw).digest()
        for i in range(0, len(block), 4):
            if len(values) >= dim:
                break
            n = int.from_bytes(block[i : i + 4], "big")
            values.append((n / 0xFFFFFFFF) * 2.0 - 1.0)
    return normalize_embedding(values, dim=dim)


@dataclass
class RagHit:
    asset_id: str
    score: float
    filename: str | None = None
    transcript_snippet: str | None = None
    type: str | None = None


def rank_assets_by_embedding(
    query_embedding: Sequence[float],
    assets: list[dict[str, Any]],
    *,
    top_k: int = 10,
    min_score: float = -1.0,
) -> list[RagHit]:
    q = normalize_embedding(query_embedding)
    hits: list[RagHit] = []
    for a in assets:
        emb = a.get("embedding")
        if not emb or not isinstance(emb, (list, tuple)):
            continue
        try:
            score = cosine_similarity(q, normalize_embedding(emb))
        except RagError:
            continue
        if score < min_score:
            continue
        tr = a.get("transcript")
        snippet = tr.strip()[:240] if isinstance(tr, str) and tr.strip() else None
        hits.append(
            RagHit(
                asset_id=str(a["id"]),
                score=float(score),
                filename=a.get("filename"),
                transcript_snippet=snippet,
                type=a.get("type"),
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: max(1, top_k)]


def search_by_text(
    query: str,
    assets: list[dict[str, Any]],
    *,
    top_k: int = 10,
    min_score: float = -1.0,
) -> list[RagHit]:
    return rank_assets_by_embedding(
        deterministic_embed(query), assets, top_k=top_k, min_score=min_score
    )


def semantic_search(
    assets: list[dict[str, Any]],
    query: str,
    *,
    top_k: int = 10,
    min_score: float = -1.0,
) -> list[RagHit]:
    """Alias used by the AI agent orchestrator."""
    return search_by_text(query, assets, top_k=top_k, min_score=min_score)
