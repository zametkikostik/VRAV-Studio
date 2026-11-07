"""Index ASR transcript segments with embeddings (Semantic Video Search Phase B)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Sequence, TYPE_CHECKING

from app.services.embeddings import EmbeddingProvider, validate_embedding_vector
from app.services.rag_search import RagError, require_embedding_vector, vector_space_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.project import Asset

MAX_SEGMENTS_PER_ASSET = 500
MAX_SEGMENT_TEXT_CHARS = 8000
BATCH_SIZE = 32


class SegmentIndexError(Exception):
    pass


class TranscriptSegmentsUnavailable(SegmentIndexError):
    """No usable timestamped ASR segments on the asset."""


@dataclass
class SegmentInput:
    index: int
    start_ms: int
    end_ms: int
    text: str


def _content_hash(start_ms: int, end_ms: int, text: str) -> str:
    raw = f"{start_ms}|{end_ms}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def extract_segments_from_asset(asset: Any) -> list[SegmentInput]:
    """Read timestamped segments from asset.metadata_.transcription.segments only."""
    meta = asset.metadata_ if isinstance(asset.metadata_, dict) else {}
    tr = meta.get("transcription") if isinstance(meta.get("transcription"), dict) else {}
    segs = tr.get("segments")
    if not isinstance(segs, list) or not segs:
        raise TranscriptSegmentsUnavailable("transcript_segments_unavailable")
    out: list[SegmentInput] = []
    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            continue
        text = (s.get("text") or "").strip()
        if not text:
            continue
        try:
            start_ms = int(s.get("start_ms", s.get("start", 0)))
            end_ms = int(s.get("end_ms", s.get("end", start_ms)))
        except (TypeError, ValueError) as e:
            raise SegmentIndexError(f"invalid segment timestamps at index {i}") from e
        if start_ms < 0 or end_ms < start_ms:
            raise SegmentIndexError(f"out-of-range timestamps at index {i}")
        if len(text) > MAX_SEGMENT_TEXT_CHARS:
            text = text[:MAX_SEGMENT_TEXT_CHARS]
        out.append(SegmentInput(index=i, start_ms=start_ms, end_ms=end_ms, text=text))
        if len(out) >= MAX_SEGMENTS_PER_ASSET:
            break
    if not out:
        raise TranscriptSegmentsUnavailable("transcript_segments_unavailable")
    return out


async def index_asset_segments(
    session: Any,
    *,
    asset: Any,
    provider: EmbeddingProvider,
) -> dict[str, Any]:
    """Idempotent: replace segment index for this asset+vector-space with current transcript."""
    from sqlalchemy import delete
    from app.models.project import TranscriptSegmentEmbedding

    segments = extract_segments_from_asset(asset)
    provider_name = getattr(provider, "name", "unknown")
    model = getattr(provider, "model", "unknown")
    dims = int(getattr(provider, "dimensions", 1536))
    space = vector_space_id(provider=provider_name, model=model, dimensions=dims)

    texts = [s.text for s in segments]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        part = await provider.embed_many(batch)
        if len(part) != len(batch):
            raise SegmentIndexError("embedding batch size mismatch")
        for v in part:
            vectors.append(validate_embedding_vector(v, expected_dim=dims, strict_dim=True))

    if len(vectors) != len(segments):
        raise SegmentIndexError("embedding count mismatch")

    await session.execute(
        delete(TranscriptSegmentEmbedding).where(
            TranscriptSegmentEmbedding.asset_id == asset.id,
            TranscriptSegmentEmbedding.embedding_provider == provider_name,
            TranscriptSegmentEmbedding.embedding_model == model,
        )
    )

    for seg, vec in zip(segments, vectors):
        row = TranscriptSegmentEmbedding(
            id=uuid.uuid4(),
            asset_id=asset.id,
            project_id=asset.project_id,
            segment_index=seg.index,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=seg.text,
            embedding=vec,
            embedding_provider=provider_name,
            embedding_model=model,
            embedding_dimensions=dims,
            content_hash=_content_hash(seg.start_ms, seg.end_ms, seg.text),
        )
        session.add(row)

    if vectors:
        meta = dict(asset.metadata_ or {})
        meta["embedding_provider"] = provider_name
        meta["embedding_model"] = model
        meta["embedding_dimensions"] = dims
        meta["embedding_space"] = space
        asset.embedding = vectors[0]
        asset.metadata_ = meta

    await session.flush()
    return {
        "ok": True,
        "asset_id": str(asset.id),
        "segments_indexed": len(segments),
        "embedding_provider": provider_name,
        "embedding_model": model,
        "embedding_dimensions": dims,
        "vector_space": space,
    }


@dataclass
class SegmentHit:
    segment_id: str
    asset_id: str
    asset_name: str | None
    start_ms: int
    end_ms: int
    snippet: str
    score: float
    embedding_model: str


async def search_project_segments(
    session: Any,
    *,
    project_id: Any,
    query_embedding: Sequence[float],
    provider_name: str,
    model: str,
    dimensions: int,
    top_k: int = 10,
    min_score: float = -1.0,
) -> list[SegmentHit]:
    """Project-scoped cosine rank over segment rows in the exact vector space."""
    from sqlalchemy import select
    from app.models.project import Asset, TranscriptSegmentEmbedding
    from app.services.rag_search import cosine_similarity, normalize_embedding

    q = require_embedding_vector(query_embedding, expected_dim=dimensions)
    qn = normalize_embedding(q, dim=dimensions, allow_resize=False)

    result = await session.execute(
        select(TranscriptSegmentEmbedding, Asset.filename)
        .join(Asset, Asset.id == TranscriptSegmentEmbedding.asset_id)
        .where(
            TranscriptSegmentEmbedding.project_id == project_id,
            TranscriptSegmentEmbedding.embedding_provider == provider_name,
            TranscriptSegmentEmbedding.embedding_model == model,
            TranscriptSegmentEmbedding.embedding_dimensions == dimensions,
            Asset.deleted_at.is_(None),
            Asset.project_id == project_id,
        )
    )
    rows = result.all()
    hits: list[SegmentHit] = []
    for seg, filename in rows:
        try:
            e = require_embedding_vector(seg.embedding, expected_dim=dimensions)
            en = normalize_embedding(e, dim=dimensions, allow_resize=False)
            score = cosine_similarity(qn, en)
        except RagError:
            continue
        if score < min_score:
            continue
        hits.append(
            SegmentHit(
                segment_id=str(seg.id),
                asset_id=str(seg.asset_id),
                asset_name=filename,
                start_ms=int(seg.start_ms),
                end_ms=int(seg.end_ms),
                snippet=(seg.text or "")[:240],
                score=float(score),
                embedding_model=seg.embedding_model,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: max(1, min(int(top_k), 50))]
