"""Prometheus metrics exposition (+ legacy in-process counters for compatibility)."""
from __future__ import annotations

import time
from collections import Counter

from fastapi import APIRouter, Header, HTTPException, Response

from app.core.config import get_settings
from app.core.metrics import note_http, normalize_path, render_metrics

router = APIRouter(tags=["metrics"])

_start = time.time()
REQUESTS: Counter[str] = Counter()
ERRORS: Counter[str] = Counter()
_MAX_KEYS = 500


def note_request(method: str, path: str, status: int, duration_s: float | None = None) -> None:
    path_n = normalize_path(path)
    key = f"{method}:{path_n}:{status}"
    if key not in REQUESTS and len(REQUESTS) >= _MAX_KEYS:
        pass
    else:
        REQUESTS[key] += 1
        if status >= 500:
            ek = f"{method}:{path_n}"
            if ek not in ERRORS and len(ERRORS) >= _MAX_KEYS:
                pass
            else:
                ERRORS[ek] += 1
    note_http(method, path_n, status, duration_s if duration_s is not None else 0.0)


@router.get("/metrics")
async def metrics(authorization: str | None = Header(default=None)):
    settings = get_settings()
    token = (getattr(settings, "metrics_token", None) or "").strip()
    if token:
        expected = f"Bearer {token}"
        if (authorization or "") != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")
    body, ctype = render_metrics()
    extra = (
        f"\n# HELP vrav_up 1 if process is up\n"
        f"# TYPE vrav_up gauge\n"
        f"vrav_up 1\n"
        f"# HELP vrav_process_uptime_seconds Uptime\n"
        f"# TYPE vrav_process_uptime_seconds gauge\n"
        f"vrav_process_uptime_seconds {time.time() - _start:.0f}\n"
    ).encode()
    return Response(content=body + extra, media_type=ctype)
