"""Fix 2: production rate limiter fail-closed behavior."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest


def test_build_prod_rejects_memory_backend():
    from app.core.rate_limit import build_auth_limiter

    with patch.dict(os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_BACKEND": "memory"}, clear=False):
        with pytest.raises(RuntimeError, match="not allowed"):
            build_auth_limiter()


def test_build_prod_uses_redis_without_fallback():
    from app.core.rate_limit import RedisSlidingWindowLimiter, build_auth_limiter

    with patch.dict(os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_BACKEND": "auto"}, clear=False):
        lim = build_auth_limiter()
        assert isinstance(lim, RedisSlidingWindowLimiter)
        assert lim.allow_memory_fallback is False
        assert lim._fallback is None


def test_redis_limiter_denies_when_no_fallback_and_no_client():
    from app.core.rate_limit import RedisSlidingWindowLimiter

    lim = RedisSlidingWindowLimiter(max_calls=10, allow_memory_fallback=False)
    lim._redis = None

    def _broken_client():
        return None

    lim._client = _broken_client  # type: ignore[method-assign]

    async def _run():
        assert await lim.allow("any") is False

    asyncio.run(_run())


def test_redis_limiter_falls_back_in_dev_when_client_missing():
    from app.core.rate_limit import RedisSlidingWindowLimiter

    lim = RedisSlidingWindowLimiter(max_calls=2, allow_memory_fallback=True)
    lim._client = lambda: None  # type: ignore[method-assign]

    async def _run():
        assert await lim.allow("k") is True
        assert await lim.allow("k") is True
        assert await lim.allow("k") is False  # memory window of 2

    asyncio.run(_run())
