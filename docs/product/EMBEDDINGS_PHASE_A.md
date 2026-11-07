# Semantic Search Phase A — EmbeddingProvider

## Providers
| `EMBEDDING_PROVIDER` | Behavior |
|----------------------|----------|
| `mock` | Deterministic hash vectors (tests only) |
| `openai` | OpenAI `text-embedding-3-small` via `/v1/embeddings` |

Production/staging **reject** mock unless `ALLOW_MOCK_EMBEDDINGS=1`.
Missing provider/key → `EmbeddingConfigError` (HTTP 503 on search). **No silent hash fallback.**

## API
`POST /projects/{id}/search` embeds the query with the configured provider, then cosine-ranks stored `Asset.embedding` values **in the same vector space**.

## Vector-space compatibility (Phase A)

Stored `Asset.embedding` values without `metadata.embedding_model` are treated as **legacy hash vectors**.

| Query provider | Asset tag | Ranked? |
|----------------|-----------|---------|
| mock | none / mock | yes (tests) |
| openai | none (legacy) | **no** |
| openai | `text-embedding-3-small` | yes |

If OpenAI is configured but no compatible asset vectors exist, search returns
`status=embeddings_not_ready` with an empty `results` list (no fake scores).

**Phase B** must re-embed transcripts with the same model and persist
`metadata.embedding_model`.
