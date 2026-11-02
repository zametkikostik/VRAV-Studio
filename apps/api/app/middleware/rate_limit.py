"""AI endpoint rate limiting middleware (Redis sliding/fixed window).

Limits (requests / 60s window, per user id or anonymous):
  POST .../generate  → 10
  POST .../search or .../rag/search → 30
  POST /ai/chat → 20

Uses Redis when available; in non-production may fall back to in-memory
(same policy as auth_limiter). Production is fail-closed.
"""
from __future__ import annotations

import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.rate_limit import RateLimitDecision, RedisSlidingWindowLimiter, SlidingWindowLimiter

logger = logging.getLogger("vrav.ai_ratelimit")

AI_LIMITS: list[tuple[str, int, str]] = [
    ("/generate", 10, "generate"),
    ("/rag/search", 30, "search"),
    ("/search", 30, "search"),
    ("/ai/chat", 20, "chat"),
]


def _build_limiter(max_calls: int) -> SlidingWindowLimiter | RedisSlidingWindowLimiter:
    env = os.getenv("ENVIRONMENT", "development").lower()
    backend = os.getenv("RATE_LIMIT_BACKEND", "auto").lower()
    if env == "production":
        return RedisSlidingWindowLimiter(
            max_calls=max_calls, window_seconds=60, allow_memory_fallback=False
        )
    if backend in ("memory", "local"):
        return SlidingWindowLimiter(max_calls=max_calls, window_seconds=60)
    return RedisSlidingWindowLimiter(
        max_calls=max_calls, window_seconds=60, allow_memory_fallback=True
    )


class AIRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limiters: dict[str, SlidingWindowLimiter | RedisSlidingWindowLimiter] | None = None,
    ):
        super().__init__(app)
        self._limiters = limiters or {
            "generate": _build_limiter(10),
            "search": _build_limiter(30),
            "chat": _build_limiter(20),
        }

    def _match(self, path: str, method: str) -> tuple[int, str] | None:
        if method.upper() != "POST":
            return None
        for fragment, limit, name in AI_LIMITS:
            if fragment in path:
                return limit, name
        return None

    def _user_key(self, request: Request) -> str:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            try:
                from app.core.security import decode_access_token

                sub = decode_access_token(token)
                if sub:
                    return f"user:{sub}"
            except Exception:
                pass
        peer = request.client.host if request.client else "unknown"
        return f"anon:{peer}"

    async def dispatch(self, request: Request, call_next) -> Response:
        matched = self._match(request.url.path, request.method)
        if matched is None:
            return await call_next(request)

        limit, bucket = matched
        limiter = self._limiters.get(bucket) or _build_limiter(limit)
        user_key = self._user_key(request)
        rl_key = f"rate_limit:{user_key}:{bucket}"

        decision: RateLimitDecision = await limiter.allow_detail(rl_key)
        if not decision.allowed:
            retry = max(1, decision.reset_at - int(time.time()))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(decision.reset_at),
                    "Retry-After": str(retry),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Reset"] = str(decision.reset_at)
        return response
