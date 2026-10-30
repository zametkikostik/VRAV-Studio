from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("vrav.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status = getattr(response, "status_code", 500) if response else 500
            logger.info(
                "%s %s -> %s %.1fms",
                request.method,
                request.url.path,
                status,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            try:
                from app.api.metrics import note_request

                note_request(request.method, request.url.path, status)
            except Exception:
                pass
            if response is not None:
                response.headers["X-Request-ID"] = request_id
