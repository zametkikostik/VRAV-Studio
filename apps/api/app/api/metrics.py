"""Prometheus-style metrics."""
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
        f"vrav_process_uptime_seconds {time.time() - _start:.0f}",
        "# TYPE vrav_http_requests_total counter",
    ]
    for key, val in sorted(REQUESTS.items()):
        method, path, status = key.split(":", 2)
        path_l = path.replace('"', "")
        lines.append(
            f'vrav_http_requests_total{{method="{method}",path="{path_l}",status="{status}"}} {val}'
        )
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
