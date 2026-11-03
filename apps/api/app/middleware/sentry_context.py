"""Attach lightweight user/request tags to Sentry scope (no PII beyond user id)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SentryContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            import sentry_sdk

            user_id = None
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                try:
                    from app.core.security import decode_access_token

                    user_id = decode_access_token(auth[7:].strip())
                except Exception:
                    user_id = None
            if user_id:
                sentry_sdk.set_user({"id": str(user_id)})
            else:
                sentry_sdk.set_user(None)
            sentry_sdk.set_tag("http.method", request.method)
            path = request.url.path
            if len(path) > 120:
                path = path[:120]
            sentry_sdk.set_tag("http.path", path)
        except Exception:
            pass
        return await call_next(request)
