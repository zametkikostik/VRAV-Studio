"""Phase A: EmbeddingProvider — mocked HTTP, no real API keys."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.services.embeddings import (
    EmbeddingAuthError,
    EmbeddingProviderError,
    EmbeddingUnavailableError,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
    validate_embedding_vector,
)


def test_validate_vector_ok():
    v = validate_embedding_vector([0.1] * 8, expected_dim=8)
    assert len(v) == 8


def test_validate_wrong_dim():
    with pytest.raises(EmbeddingProviderError, match="dimension"):
        validate_embedding_vector([0.1, 0.2], expected_dim=8)


def test_validate_nan():
    with pytest.raises(EmbeddingProviderError, match="non-finite"):
        validate_embedding_vector([0.0, float("nan")], expected_dim=2)


def test_validate_inf():
    with pytest.raises(EmbeddingProviderError, match="non-finite"):
        validate_embedding_vector([1.0, float("inf")], expected_dim=2)


def test_validate_non_numeric():
    with pytest.raises(EmbeddingProviderError, match="non-numeric"):
        validate_embedding_vector([0.1, "x"], expected_dim=2)


def test_mock_provider_deterministic():
    p = MockEmbeddingProvider(dimensions=32)
    a, b = asyncio.run(p.embed(["same text", "same text"]))
    assert a == b
    assert len(a) == 32


def test_get_provider_mock_explicit(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    assert isinstance(get_embedding_provider(), MockEmbeddingProvider)


def test_get_provider_test_env_defaults_mock(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert isinstance(get_embedding_provider(), MockEmbeddingProvider)


def test_production_requires_provider(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(EmbeddingUnavailableError, match="not configured"):
        get_embedding_provider()


def test_production_rejects_silent_hash(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    with pytest.raises(EmbeddingUnavailableError):
        get_embedding_provider()


def test_openai_requires_key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(EmbeddingUnavailableError, match="OPENAI_API_KEY"):
        get_embedding_provider()


def test_openai_success_mocked():
    dim = 8
    vec = [0.01 * i for i in range(dim)]

    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "embedding": vec, "object": "embedding"}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=dim, max_retries=0)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        out = asyncio.run(prov.embed(["hello world"]))
    assert len(out) == 1
    assert out[0] == vec


def test_openai_missing_embedding_field():
    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "object": "embedding"}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk", dimensions=8, max_retries=0)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="missing"):
            asyncio.run(prov.embed(["hello"]))


def test_openai_wrong_dimensions():
    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk", dimensions=8, max_retries=0)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="dimension"):
            asyncio.run(prov.embed(["hello"]))


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

    prov = OpenAIEmbeddingProvider(api_key="bad", dimensions=8, max_retries=2)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingAuthError):
            asyncio.run(prov.embed(["hello"]))


def test_openai_429_exhausted():
    class FakeResp:
        status_code = 429

        def json(self):
            return {"error": "rate"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIEmbeddingProvider(api_key="sk", dimensions=8, max_retries=1)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="429"):
            asyncio.run(prov.embed(["hello"]))


def test_openai_timeout():
    import httpx

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.TimeoutException("timeout")

    prov = OpenAIEmbeddingProvider(api_key="sk", dimensions=8, max_retries=0)
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(EmbeddingProviderError, match="timeout"):
            asyncio.run(prov.embed(["hello"]))
