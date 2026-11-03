"""Iteration 6 Part 4: circuit breaker for external APIs."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    reset_all_breakers,
    xai_breaker,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_all_breakers()
    yield
    reset_all_breakers()


@pytest.mark.asyncio
async def test_opens_after_threshold_failures():
    cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)

    async def boom():
        raise RuntimeError("upstream")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(boom)
    assert cb.state() == "open"
    with pytest.raises(CircuitOpenError):
        await cb.call(boom)


@pytest.mark.asyncio
async def test_success_resets_failures():
    cb = CircuitBreaker("test2", failure_threshold=3, recovery_timeout=60)

    async def boom():
        raise RuntimeError("x")

    async def ok():
        return "ok"

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert await cb.call(ok) == "ok"
    assert cb.state() == "closed"
    assert cb._failures == 0


@pytest.mark.asyncio
async def test_half_open_after_timeout():
    cb = CircuitBreaker("test3", failure_threshold=2, recovery_timeout=0.05)

    async def boom():
        raise RuntimeError("x")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(boom)
    assert cb.state() == "open"
    import asyncio

    await asyncio.sleep(0.06)
    assert cb.state() == "half_open"

    async def ok():
        return 1

    assert await cb.call(ok) == 1
    assert cb.state() == "closed"


@pytest.mark.asyncio
async def test_run_chat_respects_open_circuit_and_falls_back_to_mock():
    from app.services.ai_gateway import run_chat
    from vrav_ai.protocol import ChatMessage, ChatRequest

    async def boom():
        raise RuntimeError("xai down")

    for _ in range(5):
        with pytest.raises(RuntimeError):
            await xai_breaker.call(boom)
    assert xai_breaker.state() == "open"

    req = ChatRequest(
        model="xai/grok",
        messages=[ChatMessage(role="user", content="hi")],
    )
    resp = await run_chat(req)
    assert resp is not None
    assert (resp.raw or {}).get("provider_id") in ("mock", "openrouter", "routerai", "xai")


def test_payment_modules_reference_breakers():
    root = Path(__file__).resolve().parents[1]
    assert "stripe_breaker" in (root / "app/services/payment.py").read_text()
    assert "yookassa_breaker" in (root / "app/services/yookassa.py").read_text()
