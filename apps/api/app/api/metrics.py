"""Prometheus-style metrics (minimal text exposition)."""
from __future__ import annotations

import re
import time
from collections import Counter

from fastapi import APIRouter, Header, HTTPException, Response

from app.core.config import get_settings

router = APIRouter(tags=["metrics"])

_start = time.time()
REQUESTS: Counter[str] = Counter()
ERRORS: Counter[str] = Counter()
_MAX_KEYS = 500

_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX = re.compile(r"/[0-9a-fA-F]{16,}(?=/|$)")


def normalize_path(path: str) -> str:
    """Collapse UUIDs/long hex segments to templates to bound label cardinality."""
    p = _UUID.sub("{id}", path)
    p = _HEX.sub("/{id}", p)
    if len(p) > 120:
        p = p[:120]
    return p or "/"


def note_request(method: str, path: str, status: int) -> None:
    path = normalize_path(path)
    key = f"{method}:{path}:{status}"
    if key not in REQUESTS and len(REQUESTS) >= _MAX_KEYS:
        return
    REQUESTS[key] += 1
    if status >= 500:
        ek = f"{method}:{path}"
        if ek not in ERRORS and len(ERRORS) >= _MAX_KEYS:
            return
        ERRORS[ek] += 1


@router.get("/metrics")
async def metrics(authorization: str | None = Header(default=None)):
    settings = get_settings()
    token = (getattr(settings, "metrics_token", None) or "").strip()
    if token:
        expected = f"Bearer {token}"
        if (authorization or "") != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")
    lines = [
        "# HELP vrav_up 1 if process is up",
        "# TYPE vrav_up gauge",
        "vrav_up 1",
        "# HELP vrav_process_uptime_seconds Uptime",
        "# TYPE vrav_process_uptime_seconds gauge",
        f"vrav_process_uptime_seconds {time.time() - _start:.0f}",
        "# HELP vrav_http_requests_total HTTP requests",
        "# TYPE vrav_http_requests_total counter",
    ]
    for key, val in sorted(REQUESTS.items()):
        method, path, status = key.split(":", 2)
        path_l = path.replace('"', "")
        lines.append(
            f'vrav_http_requests_total{{method="{method}",path="{path_l}",status="{status}"}} {val}'
        )
    lines.append("# HELP vrav_http_errors_total 5xx errors")
    lines.append("# TYPE vrav_http_errors_total counter")
    for key, val in sorted(ERRORS.items()):
        method, path = key.split(":", 1)
        lines.append(f'vrav_http_errors_total{{method="{method}",path="{path}"}} {val}')
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
