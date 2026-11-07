# Semantic Video Search Phase B

## Schema
Table `transcript_segment_embeddings`:
- asset_id, project_id, segment_index, start_ms, end_ms, text
- embedding (JSONB float array)
- embedding_provider, embedding_model, embedding_dimensions
- content_hash, unique (asset_id, segment_index, provider, model)
- CASCADE delete with asset/project

## Vector space identity
`{provider}::{model}::{dimensions}` — exact match only. No prefix matching. Untagged legacy hash vectors never enter OpenAI space.

## Indexing
- Celery: `vrav.media.index_segments`
- API: `POST /jobs/index-segments`
- Reads ASR segments from `asset.metadata.transcription.segments` only (no invented timestamps)
- Idempotent replace per asset+space

## Search
`POST /projects/{id}/search` ranks segment rows first; returns `start_ms`/`end_ms`/`segment_id`.
Empty index → `status=index_not_ready`, empty results.

## AI Agent
Production path fail-closed with `index_not_ready` when no compatible embeddings. Mock may fall back to non-audio assets for tests.

## Limits
JSONB + in-app cosine; project-scoped; top_k ≤ 50; batch embed 32; max 500 segments/asset.
pgvector deferred until scale requires it.
