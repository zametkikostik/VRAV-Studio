"""Extra hardening: rate limit prod, trusted proxy, security headers."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_rate_limit_prod_rejects_memory_backend():
    from app.core import rate_limit

    with patch.dict(os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_BACKEND": "memory"}, clear=False):
        with pytest.raises(RuntimeError, match="not allowed"):
            rate_limit.build_auth_limiter()


def test_rate_limit_prod_redis_no_memory_fallback():
    from app.core.rate_limit import RedisSlidingWindowLimiter, build_auth_limiter

    with patch.dict(os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_BACKEND": "redis"}, clear=False):
        lim = build_auth_limiter()
        assert isinstance(lim, RedisSlidingWindowLimiter)
        assert lim.allow_memory_fallback is False


def test_client_key_ignores_xff_from_untrusted_peer():
    from app.api.auth import _client_key
    from app.core.config import get_settings

    get_settings.cache_clear()
    with patch.dict(
        os.environ,
        {"TRUST_PROXY_HEADERS": "true", "TRUSTED_PROXIES": "10.0.0.0/8"},
        clear=False,
    ):
        get_settings.cache_clear()
        req = MagicMock()
        req.client.host = "203.0.113.9"
        req.headers.get = lambda k, default=None: "9.9.9.9" if k.lower() == "x-forwarded-for" else default
        assert _client_key(req) == "203.0.113.9"
    get_settings.cache_clear()


def test_client_key_honors_xff_from_trusted_proxy():
    from app.api.auth import _client_key
    from app.core.config import get_settings

    get_settings.cache_clear()
    with patch.dict(
        os.environ,
        {"TRUST_PROXY_HEADERS": "true", "TRUSTED_PROXIES": "10.0.0.0/8"},
        clear=False,
    ):
        get_settings.cache_clear()
        req = MagicMock()
        req.client.host = "10.1.2.3"
        req.headers.get = lambda k, default=None: "198.51.100.7" if k.lower() == "x-forwarded-for" else default
        assert _client_key(req) == "198.51.100.7"
    get_settings.cache_clear()


def test_security_headers_middleware_present():
    text = (Path(__file__).resolve().parents[1] / "app/main.py").read_text()
    assert "SecurityHeadersMiddleware" in text
    assert (Path(__file__).resolve().parents[1] / "app/middleware/security_headers.py").exists()


def test_security_checklist_exists():
    root = Path(__file__).resolve().parents[3]
    assert (root / "SECURITY_CHECKLIST.md").exists()


def test_ws_ticket_cleanup_loop_defined():
    text = (Path(__file__).resolve().parents[1] / "app/api/ws_collab.py").read_text()
    assert "_ticket_cleanup_loop" in text
