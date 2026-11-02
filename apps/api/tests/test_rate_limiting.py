"""Iteration 6: AI endpoint rate limiting."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimitDecision, SlidingWindowLimiter
from app.middleware.rate_limit import AIRateLimitMiddleware


def _app_with_limits() -> TestClient:
    app = FastAPI()

    @app.post("/projects/{project_id}/generate")
    async def generate(project_id: str):
        return {"ok": True}

    @app.post("/projects/{project_id}/rag/search")
    async def search(project_id: str):
        return {"ok": True}

    @app.post("/ai/chat")
    async def chat():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    limiters = {
        "generate": SlidingWindowLimiter(10, 60),
        "search": SlidingWindowLimiter(30, 60),
        "chat": SlidingWindowLimiter(20, 60),
    }
    app.add_middleware(AIRateLimitMiddleware, limiters=limiters)
    return TestClient(app)


def test_generate_limited_to_10():
    client = _app_with_limits()
    headers = {"Authorization": "Bearer dummy"}
    with patch("app.core.security.decode_access_token", return_value="user-1"):
        for i in range(10):
            r = client.post("/projects/p1/generate", json={"prompt": "x"}, headers=headers)
            assert r.status_code == 200, f"req {i+1}: {r.status_code}"
            assert r.headers.get("X-RateLimit-Limit") == "10"
            assert "X-RateLimit-Remaining" in r.headers
        r = client.post("/projects/p1/generate", json={"prompt": "x"}, headers=headers)
        assert r.status_code == 429
        assert r.headers.get("X-RateLimit-Limit") == "10"
        assert r.headers.get("X-RateLimit-Remaining") == "0"
        assert "Retry-After" in r.headers
        assert "X-RateLimit-Reset" in r.headers
        assert 0 < int(r.headers["Retry-After"]) <= 60


def test_search_limited_to_30():
    client = _app_with_limits()
    headers = {"Authorization": "Bearer dummy"}
    with patch("app.core.security.decode_access_token", return_value="user-2"):
        for i in range(30):
            r = client.post("/projects/p1/rag/search", json={"query": "q"}, headers=headers)
            assert r.status_code == 200, f"req {i+1}"
        r = client.post("/projects/p1/rag/search", json={"query": "q"}, headers=headers)
        assert r.status_code == 429
        assert r.headers["X-RateLimit-Limit"] == "30"


def test_chat_limited_to_20():
    client = _app_with_limits()
    headers = {"Authorization": "Bearer dummy"}
    with patch("app.core.security.decode_access_token", return_value="user-3"):
        for i in range(20):
            r = client.post("/ai/chat", json={"messages": []}, headers=headers)
            assert r.status_code == 200, f"req {i+1}"
        r = client.post("/ai/chat", json={"messages": []}, headers=headers)
        assert r.status_code == 429
        assert r.headers["X-RateLimit-Limit"] == "20"


def test_health_not_rate_limited():
    client = _app_with_limits()
    for _ in range(50):
        assert client.get("/health").status_code == 200


@pytest.mark.asyncio
async def test_sliding_window_allow_detail():
    lim = SlidingWindowLimiter(3, 60)
    d1 = await lim.allow_detail("k")
    d2 = await lim.allow_detail("k")
    d3 = await lim.allow_detail("k")
    d4 = await lim.allow_detail("k")
    assert d1.allowed and d2.allowed and d3.allowed
    assert not d4.allowed
    assert d4.remaining == 0
    assert isinstance(d4, RateLimitDecision)


def test_middleware_module_wired_in_main():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/main.py").read_text()
    assert "AIRateLimitMiddleware" in text
