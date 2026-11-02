"""Prometheus metrics for AI Gateway and HTTP layer."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("vrav.metrics")

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _PROM = True
except ImportError:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    _PROM = False


if _PROM:
    AI_REQUESTS = Counter(
        "ai_gateway_requests_total",
        "Total AI gateway requests",
        ["provider", "model", "status"],
    )
    AI_TOKENS = Counter(
        "ai_gateway_tokens_total",
        "Total tokens used",
        ["provider", "model", "type"],
    )
    AI_LATENCY = Histogram(
        "ai_gateway_latency_seconds",
        "AI gateway request latency",
        ["provider", "model"],
        buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    )
    AI_ERRORS = Counter(
        "ai_gateway_errors_total",
        "AI gateway errors",
        ["provider", "error_type"],
    )
    HTTP_REQUESTS = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path_template", "status"],
    )
    HTTP_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration",
        ["method", "path_template"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    CREDIT_RESERVATIONS_ACTIVE = Gauge(
        "credit_reservations_active",
        "Currently active credit reservations",
    )
else:  # pragma: no cover
    AI_REQUESTS = AI_TOKENS = AI_LATENCY = AI_ERRORS = HTTP_REQUESTS = HTTP_DURATION = None
    CREDIT_RESERVATIONS_ACTIVE = None

_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX = re.compile(r"/[0-9a-fA-F]{16,}(?=/|$)")


def normalize_path(path: str) -> str:
    p = _UUID.sub("{id}", path or "/")
    p = _HEX.sub("/{id}", p)
    if len(p) > 120:
        p = p[:120]
    return p or "/"


def classify_ai_error(exc: BaseException) -> str:
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    if "timeout" in name or "timeout" in msg:
        return "timeout"
    if "429" in msg or ("rate" in msg and "limit" in msg):
        return "rate_limit"
    if "401" in msg or "403" in msg or "auth" in msg or "unauthorized" in msg:
        return "auth"
    if "connect" in msg or "upstream" in msg or "http" in name:
        return "upstream"
    return "other"


def note_ai_request(
    *,
    provider: str,
    model: str,
    status: str,
    latency_s: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    error_type: str | None = None,
) -> None:
    if not _PROM:
        return
    try:
        prov = (provider or "unknown")[:64]
        mod = (model or "unknown")[:64]
        st = status if status in ("success", "error") else "error"
        AI_REQUESTS.labels(provider=prov, model=mod, status=st).inc()
        AI_LATENCY.labels(provider=prov, model=mod).observe(max(0.0, latency_s))
        if prompt_tokens:
            AI_TOKENS.labels(provider=prov, model=mod, type="prompt").inc(prompt_tokens)
        if completion_tokens:
            AI_TOKENS.labels(provider=prov, model=mod, type="completion").inc(completion_tokens)
        if st == "error" and error_type:
            AI_ERRORS.labels(provider=prov, error_type=error_type[:32]).inc()
    except Exception as e:
        logger.debug("note_ai_request failed: %s", e)


def note_http(method: str, path: str, status: int, duration_s: float) -> None:
    if not _PROM:
        return
    try:
        tmpl = normalize_path(path)
        HTTP_REQUESTS.labels(
            method=(method or "GET")[:16],
            path_template=tmpl,
            status=str(int(status)),
        ).inc()
        HTTP_DURATION.labels(method=(method or "GET")[:16], path_template=tmpl).observe(
            max(0.0, duration_s)
        )
    except Exception as e:
        logger.debug("note_http failed: %s", e)


def render_metrics() -> tuple[bytes, str]:
    if not _PROM:
        body = b"# prometheus-client not installed\n"
        return body, "text/plain; charset=utf-8"
    return generate_latest(), CONTENT_TYPE_LATEST
