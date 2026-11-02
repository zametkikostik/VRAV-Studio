"""Request logging: structured logs + optional PostgreSQL audit rows."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("vrav.request")

SKIP_PATHS = frozenset(
    {
        "/health",
        "/health/db",
        "/health/ready",
        "/health/live",
        "/metrics",
        "/favicon.ico",
    }
)


def _extract_user_id(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    try:
        from app.core.security import decode_access_token

        return decode_access_token(token)
    except Exception:
        return None


async def persist_api_request_log(fields: dict[str, Any]) -> None:
    """Best-effort async insert. Never raises to callers."""
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.api_log import ApiRequestLog

        uid = fields.get("user_id")
        oid = fields.get("organization_id")
        user_uuid = None
        org_uuid = None
        if uid:
            try:
                user_uuid = uuid.UUID(str(uid))
            except ValueError:
                user_uuid = None
        if oid:
            try:
                org_uuid = uuid.UUID(str(oid))
            except ValueError:
                org_uuid = None

        async with AsyncSessionLocal() as session:
            session.add(
                ApiRequestLog(
                    id=uuid.uuid4(),
                    method=fields["method"][:10],
                    path=fields["path"][:500],
                    query_params=fields.get("query_params"),
                    user_id=user_uuid,
                    organization_id=org_uuid,
                    status_code=int(fields["status_code"]),
                    duration_ms=float(fields["duration_ms"]),
                    user_agent=(fields.get("user_agent") or None),
                    ip_address=(fields.get("ip_address") or None),
                    request_id=(fields.get("request_id") or None),
                    error_message=(fields.get("error_message") or None),
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("api_request_log persist failed: %s", e.__class__.__name__)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status = getattr(response, "status_code", 500) if response else 500
            path = request.url.path
            logger.info(
                "%s %s -> %s %.1fms",
                request.method,
                path,
                status,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": status,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            try:
                from app.api.metrics import note_request

                note_request(request.method, path, status)
            except Exception:
                pass

            if path not in SKIP_PATHS:
                user_id = _extract_user_id(request)
                err = f"HTTP {status}" if status >= 400 else None
                fields = {
                    "method": request.method,
                    "path": path,
                    "query_params": dict(request.query_params) if request.query_params else None,
                    "user_id": user_id,
                    "organization_id": None,
                    "status_code": status,
                    "duration_ms": round(duration_ms, 3),
                    "user_agent": (request.headers.get("user-agent") or "")[:500],
                    "ip_address": request.client.host if request.client else None,
                    "request_id": request_id,
                    "error_message": err,
                }
                try:
                    await persist_api_request_log(fields)
                except Exception:
                    pass

            if response is not None:
                response.headers["X-Request-ID"] = request_id
