# Iteration 5 — RAG / semantic asset search

## Status: IN PR (`feat/iteration-5-rag-search`)

| Item | Status |
|------|--------|
| Deterministic embed + cosine rank | PASS |
| `POST /projects/{id}/rag/search` | PASS (code) |
| `POST /rag/embed` | PASS (code) |
| Migration 013 boundary | PASS (no-op, CI-safe) |
| Native pgvector index | DEFERRED (ops; needs vector extension image) |

## Why JSONB + Python rank (not mandatory pgvector in CI)

CI Postgres is `postgres:16-alpine` without the `vector` extension.
`CREATE EXTENSION vector` would fail e2e migrations.
Production can dual-write a `vector(1536)` column later without changing the API.

## Local verify

```bash
cd apps/api && env -u DATABASE_URL -u REDIS_URL \
  PYTHONPATH=".:../../packages/ai-gateway:../../packages/core" \
  SECRET_KEY=ci-secret-key-for-tests python -m pytest -q tests/
```
