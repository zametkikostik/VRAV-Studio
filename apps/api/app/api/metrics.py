"""Prometheus-style metrics (minimal text exposition)."""
from __future__ import annotations

import time
from collections import Counter

from fastapi import APIRouter, Response

router = APIRouter(tags=["metrics"])

_start = time.time()
REQUESTS = Counter()
ERRORS = Counter()


def note_request(method: str, path: str, status: int) -> None:
    REQUESTS[f"{method}:{path}:{status}"] += 1
    if status >= 500:
        ERRORS[f"{method}:{path}"] += 1


@router.get("/metrics")
async def metrics():
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
