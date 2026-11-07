# Semantic Search Phase A — EmbeddingProvider

## Providers
| `EMBEDDING_PROVIDER` | Behavior |
|----------------------|----------|
| `mock` | Deterministic hash vectors (tests only) |
| `openai` | OpenAI `text-embedding-3-small` via `/v1/embeddings` |

Production/staging **reject** mock unless `ALLOW_MOCK_EMBEDDINGS=1`.
Missing provider/key → `EmbeddingConfigError` (HTTP 503 on search). **No silent hash fallback.**

## API
`POST /projects/{id}/search` embeds the query with the configured provider, then cosine-ranks stored `Asset.embedding` values.
