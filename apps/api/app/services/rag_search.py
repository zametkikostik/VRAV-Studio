"""RAG / semantic asset search over stored embeddings (JSONB float arrays)."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Sequence

EMBEDDING_DIM = 1536


class RagError(Exception):
    pass


def require_embedding_vector(
    values: Sequence[float],
    *,
    expected_dim: int | None = None,
) -> list[float]:
    """Strict vector validation for ranking — no pad/truncate/silent repair."""
    if values is None:
        raise RagError("empty embedding")
    if not isinstance(values, (list, tuple)):
        raise RagError("embedding must be a list")
    if len(values) == 0:
        raise RagError("empty embedding")
    if expected_dim is not None and len(values) != expected_dim:
        raise RagError(
            f"embedding dimension mismatch: got {len(values)}, expected {expected_dim}"
        )
    out: list[float] = []
    for i, x in enumerate(values):
        try:
            v = float(x)
        except (TypeError, ValueError) as e:
            raise RagError(f"non-numeric embedding at index {i}") from e
        if not math.isfinite(v):
            raise RagError(f"non-finite embedding value at index {i}")
        out.append(v)
    return out


def normalize_embedding(
    values: Sequence[float],
    *,
    dim: int | None = None,
    allow_resize: bool = False,
) -> list[float]:
    """L2-normalize. Production ranking must pass allow_resize=False (default)."""
    if allow_resize:
        if not values:
            raise RagError("empty embedding")
        vec = [float(x) for x in values]
        target = dim or EMBEDDING_DIM
        if len(vec) > target:
            vec = vec[:target]
        if len(vec) < target:
            vec = vec + [0.0] * (target - len(vec))
        for v in vec:
            if not math.isfinite(v):
                raise RagError("non-finite embedding value")
    else:
        vec = require_embedding_vector(values, expected_dim=dim)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise RagError(f"cosine_similarity dimension mismatch: {len(a)} vs {len(b)}")
    if not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def vector_space_id(*, provider: str, model: str, dimensions: int) -> str:
    """Exact embedding-space identity (provider + model + dimensions)."""
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    d = int(dimensions)
    if not p or not m or d <= 0:
        raise RagError("invalid vector space identity")
    return f"{p}::{m}::{d}"


def deterministic_embed(text: str, *, dim: int = EMBEDDING_DIM) -> list[float]:
    """Hash-derived vector for tests / MockEmbeddingProvider only — not semantic."""
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
    return normalize_embedding(values, dim=dim, allow_resize=True)


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
    expected_dim: int | None = None,
) -> list[RagHit]:
    q_raw = require_embedding_vector(query_embedding, expected_dim=expected_dim)
    q = normalize_embedding(q_raw, dim=len(q_raw), allow_resize=False)
    hits: list[RagHit] = []
    for a in assets:
        emb = a.get("embedding")
        if not emb or not isinstance(emb, (list, tuple)):
            continue
        try:
            e_raw = require_embedding_vector(emb, expected_dim=len(q_raw))
            score = cosine_similarity(
                q, normalize_embedding(e_raw, dim=len(e_raw), allow_resize=False)
            )
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
    query_embedding: Sequence[float] | None = None,
) -> list[RagHit]:
    if query_embedding is None:
        from app.services.embeddings import EmbeddingConfigError, get_embedding_provider

        try:
            provider = get_embedding_provider()
        except EmbeddingConfigError as e:
            raise RagError(str(e)) from e
        embed_sync = getattr(provider, "embed_text_sync", None)
        if embed_sync is None:
            raise RagError(
                "live embedding provider requires query_embedding from async embed()"
            )
        try:
            query_embedding = embed_sync(query)
        except Exception as e:
            raise RagError(str(e)) from e
    return rank_assets_by_embedding(
        query_embedding, assets, top_k=top_k, min_score=min_score
    )


def semantic_search(
    assets: list[dict[str, Any]],
    query: str,
    *,
    top_k: int = 10,
    min_score: float = -1.0,
    query_embedding: Sequence[float] | None = None,
) -> list[RagHit]:
    return search_by_text(
        query, assets, top_k=top_k, min_score=min_score, query_embedding=query_embedding
    )


def filter_assets_for_embedding_space(
    assets: list[dict[str, Any]],
    *,
    provider_name: str,
    model: str,
    dimensions: int | None = None,
) -> list[dict[str, Any]]:
    """Keep assets whose stored vectors match exact vector_space_id."""
    dims = int(dimensions) if dimensions is not None else EMBEDDING_DIM
    try:
        target = vector_space_id(provider=provider_name, model=model, dimensions=dims)
    except RagError:
        return []
    provider_name = (provider_name or "").strip().lower()
    out: list[dict[str, Any]] = []
    for a in assets:
        emb = a.get("embedding")
        if not emb or not isinstance(emb, (list, tuple)):
            continue
        meta = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
        sp = a.get("embedding_provider") or meta.get("embedding_provider")
        sm = a.get("embedding_model") or meta.get("embedding_model")
        sd = a.get("embedding_dimensions") or meta.get("embedding_dimensions")
        if sp and sm:
            try:
                sd_i = int(sd) if sd is not None else len(emb)
                if vector_space_id(provider=str(sp), model=str(sm), dimensions=sd_i) == target:
                    out.append(a)
            except (RagError, TypeError, ValueError):
                continue
            continue
        if provider_name in ("mock", "deterministic", "hash", "test") and not sp and not sm:
            if len(emb) == dims:
                out.append(a)
    return out


def search_by_text_sync_mock(
    query: str,
    assets: list[dict[str, Any]],
    *,
    top_k: int = 10,
    min_score: float = -1.0,
) -> list[RagHit]:
    """Test-only helper: rank using MockEmbeddingProvider (hash) on both sides."""
    from app.services.embeddings import MockEmbeddingProvider

    provider = MockEmbeddingProvider()
    q = provider.embed_text_sync(query)
    compatible = filter_assets_for_embedding_space(
        assets,
        provider_name=provider.name,
        model=provider.model,
        dimensions=getattr(provider, "dimensions", EMBEDDING_DIM),
    )
    return rank_assets_by_embedding(q, compatible, top_k=top_k, min_score=min_score)
