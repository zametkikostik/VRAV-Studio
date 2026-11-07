"""Embedding providers for Semantic Search Phase A.

Production must use a real provider (OpenAI text-embedding-3-small).
Hash-based vectors are restricted to explicit mock / test environments.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Protocol, Sequence

import httpx

logger = logging.getLogger(__name__)

DEFAULT_DIM = 1536
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"


class EmbeddingError(Exception):
    """Base embedding failure."""


class EmbeddingConfigError(EmbeddingError):
    """Missing or invalid provider configuration (no silent fallback)."""


class EmbeddingProviderError(EmbeddingError):
    """Upstream or validation failure."""


class EmbeddingAuthError(EmbeddingProviderError):
    """Permanent auth failure — do not retry as configuration success."""


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    async def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for text."""
        ...

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings aligned with input order."""
        ...


def validate_embedding_vector(
    values: Sequence[Any],
    *,
    expected_dim: int = DEFAULT_DIM,
    strict_dim: bool = True,
) -> list[float]:
    """Validate numeric finite vector; optionally require exact dimensions."""
    if values is None:
        raise EmbeddingProviderError("missing embedding vector")
    if not isinstance(values, (list, tuple)):
        raise EmbeddingProviderError("embedding must be a list of numbers")
    if len(values) == 0:
        raise EmbeddingProviderError("empty embedding vector")
    if strict_dim and len(values) != expected_dim:
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
    """Deterministic hash embeddings — tests / explicit mock only. Not semantic."""

    name = "mock"
    model = "deterministic-hash"
    dimensions = DEFAULT_DIM

    def __init__(self, *, dim: int = DEFAULT_DIM) -> None:
        self.dimensions = dim

    def embed_text_sync(self, text: str) -> list[float]:
        from app.services.rag_search import deterministic_embed

        return deterministic_embed(text, dim=self.dimensions)

    async def embed(self, text: str) -> list[float]:
        return self.embed_text_sync(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text_sync(t) for t in texts]


class OpenAIEmbeddingProvider:
    """OpenAI Embeddings API (text-embedding-3-small by default)."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        dimensions: int = DEFAULT_DIM,
        timeout_s: float = 60.0,
        base_url: str | None = None,
    ) -> None:
        if not (api_key or "").strip():
            raise EmbeddingConfigError("OPENAI_API_KEY is required for openai embedding provider")
        self.api_key = api_key.strip()
        self.model = (model or os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_OPENAI_MODEL).strip()
        self.dimensions = int(dimensions)
        self.timeout_s = timeout_s
        self.base_url = (base_url or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip(
            "/"
        )

    def embed_text_sync(self, text: str) -> list[float]:
        raise EmbeddingConfigError(
            "OpenAI embeddings require async embed(); cannot use sync hash fallback"
        )

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        cleaned = [(t or "").strip() for t in texts]
        if not cleaned or any(not t for t in cleaned):
            raise EmbeddingProviderError("text is required for embedding")
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {"model": self.model, "input": cleaned if len(cleaned) > 1 else cleaned[0]}
        if self.model.startswith("text-embedding-3"):
            body["dimensions"] = self.dimensions

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as e:
            raise EmbeddingProviderError("OpenAI embeddings request timed out") from e
        except httpx.HTTPError as e:
            raise EmbeddingProviderError(f"OpenAI embeddings transport error: {type(e).__name__}") from e

        if resp.status_code in (401, 403):
            raise EmbeddingAuthError("OpenAI embedding authentication failed")
        if resp.status_code == 429:
            raise EmbeddingProviderError("OpenAI embedding rate limited (429)")
        if resp.status_code >= 500:
            raise EmbeddingProviderError(f"OpenAI embedding upstream error HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise EmbeddingProviderError(f"OpenAI embedding HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as e:
            raise EmbeddingProviderError("OpenAI embedding response is not JSON") from e
        if not isinstance(payload, dict):
            raise EmbeddingProviderError("OpenAI embedding response must be an object")
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise EmbeddingProviderError("OpenAI embedding response missing data")

        try:
            ordered = sorted(data, key=lambda d: int(d.get("index", 0)) if isinstance(d, dict) else 0)
        except Exception:
            ordered = data

        vectors: list[list[float]] = []
        for item in ordered:
            if not isinstance(item, dict):
                raise EmbeddingProviderError("OpenAI embedding item invalid")
            raw_vec = item.get("embedding")
            vectors.append(
                validate_embedding_vector(raw_vec, expected_dim=self.dimensions, strict_dim=True)
            )
        if len(vectors) != len(cleaned):
            raise EmbeddingProviderError(
                f"OpenAI embedding count mismatch: got {len(vectors)}, expected {len(cleaned)}"
            )
        return vectors


def _env_name() -> str:
    return (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").strip().lower()


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    """Resolve embedding provider.

    EMBEDDING_PROVIDER=mock|openai
    Production/staging: mock is refused unless ALLOW_MOCK_EMBEDDINGS=1.
    Missing config → EmbeddingConfigError (no hash fallback).
    """
    chosen = (name or os.getenv("EMBEDDING_PROVIDER") or "").strip().lower()
    env = _env_name()

    if not chosen:
        if env in ("test", "ci"):
            chosen = "mock"
        else:
            raise EmbeddingConfigError(
                "EMBEDDING_PROVIDER is not set (use openai for production, mock only for tests)"
            )

    if chosen in ("mock", "deterministic", "hash", "test"):
        if env in ("production", "prod", "staging") and os.getenv("ALLOW_MOCK_EMBEDDINGS", "").strip() != "1":
            raise EmbeddingConfigError(
                "mock embeddings are not allowed in production/staging "
                "(set EMBEDDING_PROVIDER=openai or ALLOW_MOCK_EMBEDDINGS=1 only for controlled drills)"
            )
        return MockEmbeddingProvider()

    if chosen in ("openai", "openai_embeddings"):
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise EmbeddingConfigError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        dim = int(os.getenv("EMBEDDING_DIMENSIONS") or DEFAULT_DIM)
        timeout = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS") or "60")
        return OpenAIEmbeddingProvider(api_key=key, dimensions=dim, timeout_s=timeout)

    raise EmbeddingConfigError(
        f"unsupported EMBEDDING_PROVIDER={chosen!r} (supported: openai, mock)"
    )
