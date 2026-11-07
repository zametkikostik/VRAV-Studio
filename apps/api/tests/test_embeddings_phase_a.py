"""Phase A: EmbeddingProvider — mocked HTTP only."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.services.embeddings import (
    DEFAULT_DIM,
    EmbeddingAuthError,
    EmbeddingConfigError,
    EmbeddingProviderError,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
    validate_embedding_vector,
)


def test_validate_vector_ok():
    v = [0.1] * DEFAULT_DIM
    out = validate_embedding_vector(v, expected_dim=DEFAULT_DIM)
    assert len(out) == DEFAULT_DIM


def test_validate_wrong_dimensions():
    with pytest.raises(EmbeddingProviderError, match="dimension"):
        validate_embedding_vector([0.1, 0.2], expected_dim=DEFAULT_DIM)


def test_validate_nan():
    v = [0.0] * DEFAULT_DIM
    v[3] = float("nan")
    with pytest.raises(EmbeddingProviderError, match="non-finite"):
        validate_embedding_vector(v, expected_dim=DEFAULT_DIM)


def test_validate_inf():
    v = [0.0] * DEFAULT_DIM
    v[1] = float("inf")
    with pytest.raises(EmbeddingProviderError, match="non-finite"):
        validate_embedding_vector(v, expected_dim=DEFAULT_DIM)


def test_validate_non_numeric():
    v = [0.0] * DEFAULT_DIM
    v[0] = "x"  # type: ignore
    with pytest.raises(EmbeddingProviderError, match="non-numeric"):
        validate_embedding_vector(v, expected_dim=DEFAULT_DIM)


def test_validate_missing():
    with pytest.raises(EmbeddingProviderError, match="missing"):
        validate_embedding_vector(None, expected_dim=DEFAULT_DIM)  # type: ignore


def test_mock_provider_deterministic():
    p = MockEmbeddingProvider()
    a = asyncio.run(p.embed("hello"))
    b = asyncio.run(p.embed("hello"))
    c = asyncio.run(p.embed("other"))
    assert a == b
    assert a != c
    assert len(a) == DEFAULT_DIM


def test_get_provider_mock_in_test_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    p = get_embedding_provider()
    assert isinstance(p, MockEmbeddingProvider)


def test_get_provider_explicit_mock(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    p = get_embedding_provider()
    assert isinstance(p, MockEmbeddingProvider)


def test_production_rejects_mock(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.delenv("ALLOW_MOCK_EMBEDDINGS", raising=False)
    with pytest.raises(EmbeddingConfigError, match="mock embeddings are not allowed"):
        get_embedding_provider()


def test_production_requires_provider(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    with pytest.raises(EmbeddingConfigError, match="EMBEDDING_PROVIDER is not set"):
        get_embedding_provider()


def test_openai_requires_api_key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(EmbeddingConfigError, match="OPENAI_API_KEY"):
        get_embedding_provider()


def test_openai_success_mocked():
    vec = [0.01 * (i % 10) for i in range(DEFAULT_DIM)]

    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "embedding": vec}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=DEFAULT_DIM)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        out = asyncio.run(prov.embed("hello world"))
    assert len(out) == DEFAULT_DIM
    assert out[0] == pytest.approx(0.0)


def test_openai_auth_error():
    class FakeResp:
        status_code = 401

        def json(self):
            return {"error": "nope"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="bad")
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingAuthError):
            asyncio.run(prov.embed("x"))


def test_openai_rate_limit_429():
    class FakeResp:
        status_code = 429

        def json(self):
            return {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk")
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="429"):
            asyncio.run(prov.embed("x"))


def test_openai_timeout():
    import httpx

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.TimeoutException("timeout")

    prov = OpenAIEmbeddingProvider(api_key="sk")
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="timed out"):
            asyncio.run(prov.embed("x"))


def test_openai_malformed_missing_vector():
    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk")
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="missing embedding"):
            asyncio.run(prov.embed("x"))


def test_openai_wrong_dimensions_in_response():
    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk", dimensions=DEFAULT_DIM)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="dimension"):
            asyncio.run(prov.embed("x"))


def test_openai_sync_path_refuses_hash_fallback():
    prov = OpenAIEmbeddingProvider(api_key="sk")
    with pytest.raises(EmbeddingConfigError, match="async embed"):
        prov.embed_text_sync("x")


def test_search_by_text_still_works_with_mock(monkeypatch):
    from app.services.rag_search import deterministic_embed, search_by_text

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    q = "beach sunset"
    assets = [
        {"id": "1", "embedding": deterministic_embed(q), "filename": "a.mp4", "transcript": "beach"},
        {"id": "2", "embedding": deterministic_embed("kitchen recipe"), "filename": "b.mp4"},
    ]
    hits = search_by_text(q, assets, top_k=2)
    assert hits and hits[0].asset_id == "1"
