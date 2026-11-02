"""Iteration 6 Part 3: Prometheus AI + HTTP metrics."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.metrics import (
    AI_ERRORS,
    AI_REQUESTS,
    classify_ai_error,
    note_ai_request,
    note_http,
    normalize_path,
    render_metrics,
)
from app.main import create_app
from vrav_ai.protocol import ChatMessage, ChatRequest, ChatResponse


def test_normalize_path_strips_uuid():
    p = normalize_path("/projects/11111111-1111-1111-1111-111111111111/generate")
    assert "{id}" in p
    assert "11111111" not in p


def test_classify_timeout():
    assert classify_ai_error(TimeoutError("x")) == "timeout"


def test_render_metrics_contains_ai_series():
    note_ai_request(provider="mock", model="mock/default", status="success", latency_s=0.01)
    body, ctype = render_metrics()
    text = body.decode()
    assert "ai_gateway_requests_total" in text
    assert "text/plain" in ctype or "0.0.4" in ctype


def test_metrics_endpoint_ok():
    app = create_app()
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "ai_gateway_requests_total" in r.text or "vrav_up" in r.text


@pytest.mark.asyncio
async def test_run_chat_increments_success():
    from app.services.ai_gateway import run_chat

    before = _counter_value(AI_REQUESTS, provider="mock", model="mock/default", status="success")
    req = ChatRequest(
        model="mock/default",
        messages=[ChatMessage(role="user", content="hi")],
    )
    resp = await run_chat(req)
    assert isinstance(resp, ChatResponse)
    after = _counter_value(AI_REQUESTS, provider="mock", model="mock/default", status="success")
    assert after >= before + 1


@pytest.mark.asyncio
async def test_run_chat_error_increments_errors():
    from app.services import ai_gateway as ag

    before = _counter_value(AI_ERRORS, provider="mock", error_type="timeout")

    class BoomRouter:
        async def chat(self, request):
            raise TimeoutError("upstream timeout")

    with patch.object(ag, "get_router", return_value=BoomRouter()):
        req = ChatRequest(
            model="mock/default",
            messages=[ChatMessage(role="user", content="x")],
        )
        with pytest.raises(TimeoutError):
            await ag.run_chat(req)

    after = _counter_value(AI_ERRORS, provider="mock", error_type="timeout")
    assert after >= before + 1


def test_http_note_safe():
    note_http("GET", "/health", 200, 0.001)
    body, _ = render_metrics()
    assert b"http_requests_total" in body


def test_metrics_without_redis():
    app = create_app()
    client = TestClient(app)
    assert client.get("/metrics").status_code == 200


def _counter_value(counter, **labels) -> float:
    try:
        return float(counter.labels(**labels)._value.get())
    except Exception:
        body, _ = render_metrics()
        return 0.0 if counter._name.encode() not in body else 1.0
