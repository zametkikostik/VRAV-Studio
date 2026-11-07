"""Embedding providers for semantic search (Phase A).

Production: real provider only (OpenAI text-embedding-3-small).
Mock/hash embeddings: tests or EMBEDDING_PROVIDER=mock exclusively.
Never silently fall back to hash vectors in production.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Protocol, Sequence

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536


class EmbeddingError(Exception):
    """Base embedding failure."""


class EmbeddingUnavailableError(EmbeddingError):
    """Provider not configured for this environment."""


class EmbeddingAuthError(EmbeddingError):
    """Invalid API key — do not retry."""


class EmbeddingProviderError(EmbeddingError):
    """Upstream or validation failure."""


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text (same order)."""
        ...


def validate_embedding_vector(
    values: Any,
    *,
    expected_dim: int,
) -> list[float]:
    """Reject wrong length, non-numeric, NaN, and Inf values."""
    if not isinstance(values, (list, tuple)):
        raise EmbeddingProviderError("embedding must be a list of numbers")
    if len(values) != expected_dim:
        raise EmbeddingProviderError(
            f"embedding dimension mismatch: got {len(values)}, expected {expected_dim}"
        )
    out: list[float] = []
    for i, x in enumerate(values):
        try:
            v = float(x)
        except (TypeError, ValueError) as e:
            raise EmbeddingProviderError(f"non-numeric embedding at index {i}") from e
        if not math.isfinite(v):
            raise EmbeddingProviderError(f"non-finite embedding value at index {i}")
        out.append(v)
    return out


class MockEmbeddingProvider:
    """Deterministic hash embeddings — tests / explicit mock only."""

    def __init__(self, *, dimensions: int = DEFAULT_DIM) -> None:
        self.model = "mock-hash"
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        from app.services.rag_search import deterministic_embed

        if not texts:
            return []
        out: list[list[float]] = []
        for t in texts:
            if not (t or "").strip():
                raise EmbeddingProviderError("empty text cannot be embedded")
            out.append(deterministic_embed(t, dim=self.dimensions))
        return out


class OpenAIEmbeddingProvider:
    """OpenAI Embeddings API (text-embedding-3-small by default)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        dimensions: int = DEFAULT_DIM,
        timeout_s: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        if not (api_key or "").strip():
            raise EmbeddingUnavailableError("OPENAI_API_KEY is required for openai embeddings")
        self.api_key = api_key.strip()
        self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_OPENAI_EMBED_MODEL
        self.dimensions = int(dimensions)
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        cleaned = [(t or "").strip() for t in texts]
        if not cleaned or any(not t for t in cleaned):
            raise EmbeddingProviderError("all texts must be non-empty")

        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {"model": self.model, "input": cleaned}
        if self.model.startswith("text-embedding-3"):
            body["dimensions"] = self.dimensions

        last_err: Exception | None = None
        attempts = 1 + max(0, self.max_retries)
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.post(url, headers=headers, json=body)
                if resp.status_code in (401, 403):
                    raise EmbeddingAuthError("OpenAI embedding authentication failed")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_err = EmbeddingProviderError(f"OpenAI embeddings HTTP {resp.status_code}")
                    continue
                if resp.status_code >= 400:
                    raise EmbeddingProviderError(f"OpenAI embeddings HTTP {resp.status_code}")
                try:
                    payload = resp.json()
                except Exception as e:
                    raise EmbeddingProviderError("OpenAI embeddings invalid JSON") from e
                return self._parse_response(payload, expected_count=len(cleaned))
            except (EmbeddingAuthError, EmbeddingUnavailableError):
                raise
            except EmbeddingProviderError as e:
                last_err = e
                if "HTTP 4" in str(e) and "429" not in str(e):
                    raise
            except httpx.TimeoutException:
                last_err = EmbeddingProviderError("OpenAI embeddings timeout")
                logger.warning("embedding timeout attempt %s", attempt)
            except Exception as e:
                last_err = EmbeddingProviderError(f"OpenAI embeddings failed: {type(e).__name__}")
                logger.warning("embedding attempt %s failed: %s", attempt, type(e).__name__)
        raise EmbeddingProviderError(str(last_err) if last_err else "OpenAI embeddings failed")

    def _parse_response(self, payload: Any, *, expected_count: int) -> list[list[float]]:
        if not isinstance(payload, dict):
            raise EmbeddingProviderError("OpenAI embeddings response must be an object")
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != expected_count:
            raise EmbeddingProviderError(
                f"OpenAI embeddings data length mismatch: expected {expected_count}"
            )
        indexed: list[tuple[int, list[float]]] = []
        for item in data:
            if not isinstance(item, dict):
                raise EmbeddingProviderError("OpenAI embedding item must be an object")
            emb = item.get("embedding")
            if emb is None:
                raise EmbeddingProviderError("OpenAI embedding vector missing")
            vec = validate_embedding_vector(emb, expected_dim=self.dimensions)
            try:
                idx = int(item.get("index", len(indexed)))
            except (TypeError, ValueError):
                idx = len(indexed)
            indexed.append((idx, vec))
        indexed.sort(key=lambda x: x[0])
        return [v for _, v in indexed]


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    """Resolve embedding provider from env.

    EMBEDDING_PROVIDER=mock|openai
    Production must set openai + OPENAI_API_KEY.
    Mock only when explicitly requested or ENVIRONMENT is test/ci.
    """
    chosen = (name or os.getenv("EMBEDDING_PROVIDER") or "").strip().lower()
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()

    if chosen in ("mock", "test", "hash", "deterministic"):
        return MockEmbeddingProvider()

    if not chosen:
        if env in ("test", "ci"):
            return MockEmbeddingProvider()
        raise EmbeddingUnavailableError(
            "EMBEDDING_PROVIDER is not configured (set openai or mock; "
            "production must not rely on hash embeddings)"
        )

    if chosen in ("openai", "openai_embeddings"):
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise EmbeddingUnavailableError("OPENAI_API_KEY is required for openai embeddings")
        model = os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_OPENAI_EMBED_MODEL
        dim = int(os.getenv("EMBEDDING_DIM") or DEFAULT_DIM)
        timeout_s = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS") or "60")
        retries = int(os.getenv("EMBEDDING_MAX_RETRIES") or "2")
        return OpenAIEmbeddingProvider(
            api_key=key,
            model=model,
            dimensions=dim,
            timeout_s=timeout_s,
            max_retries=retries,
        )

    raise EmbeddingUnavailableError(
        f"embedding provider '{chosen}' is not supported (use openai|mock)"
    )
