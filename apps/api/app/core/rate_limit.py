"""Rate limiter: Redis multi-replica; in-memory only in development."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque

logger = logging.getLogger("vrav.ratelimit")


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True


class RedisSlidingWindowLimiter:
    """Fixed-window counter via Redis INCR + EXPIRE (multi-replica safe)."""

    def __init__(
        self,
        max_calls: int,
        window_seconds: int = 60,
        redis_url: str | None = None,
        *,
        allow_memory_fallback: bool = True,
    ):
        self.max_calls = max_calls
        self.window = window_seconds
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.allow_memory_fallback = allow_memory_fallback
        self._redis = None
        self._fallback = SlidingWindowLimiter(max_calls, window_seconds) if allow_memory_fallback else None

    def _client(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            return self._redis
        except Exception as e:
            logger.warning("Redis rate limiter client init failed: %s", e)
            return None

    async def allow(self, key: str) -> bool:
        client = self._client()
        if client is None:
            if self._fallback is not None:
                return await self._fallback.allow(key)
            logger.error("Redis rate limiter unavailable; denying request")
            return False
        rkey = f"rl:{key}"
        try:
            n = await client.incr(rkey)
            if n == 1:
                await client.expire(rkey, self.window)
            return n <= self.max_calls
        except Exception as e:
            logger.warning("Redis rate limit error: %s", e)
            if self._fallback is not None:
                return await self._fallback.allow(key)
            return False


def build_auth_limiter() -> SlidingWindowLimiter | RedisSlidingWindowLimiter:
    max_calls = int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "30"))
    env = os.getenv("ENVIRONMENT", "development").lower()
    use_redis = os.getenv("RATE_LIMIT_BACKEND", "auto").lower()
    if env == "production":
        if use_redis in ("memory", "local"):
            raise RuntimeError("RATE_LIMIT_BACKEND=memory is not allowed in production")
        return RedisSlidingWindowLimiter(
            max_calls=max_calls, window_seconds=60, allow_memory_fallback=False
        )
    if use_redis in ("redis", "auto"):
        return RedisSlidingWindowLimiter(
            max_calls=max_calls, window_seconds=60, allow_memory_fallback=True
        )
    return SlidingWindowLimiter(max_calls=max_calls, window_seconds=60)


auth_limiter = build_auth_limiter()
