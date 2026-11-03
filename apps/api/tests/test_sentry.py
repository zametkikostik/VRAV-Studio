"""Iteration 6 Part 5: Sentry optional integration."""
from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.sentry_setup import filter_sensitive_data, init_sentry


def test_filter_sensitive_data_redacts_auth_and_password():
    event = {
        "request": {
            "headers": {"Authorization": "Bearer secret-token", "Content-Type": "application/json"},
            "data": {"password": "secret123", "email": "a@b.c"},
        }
    }
    filtered = filter_sensitive_data(event, {})
    assert filtered is not None
    assert filtered["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert filtered["request"]["data"]["password"] == "[REDACTED]"
    assert filtered["request"]["data"]["email"] == "a@b.c"


def test_init_sentry_noop_without_dsn():
    class S:
        sentry_dsn = ""
        sentry_environment = "test"
        sentry_traces_sample_rate = 0.0
        environment = "test"

    assert init_sentry(S()) is False


def test_health_sentry_disabled_without_dsn():
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
        get_settings.cache_clear()
        app = create_app()
        client = TestClient(app)
        r = client.get("/health/sentry")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "disabled"


def test_health_sentry_ok_with_mocked_sdk(monkeypatch):
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("SENTRY_DSN", "https://abc@example.com/1")
    get_settings.cache_clear()

    with patch("app.core.sentry_setup.init_sentry", return_value=True):
        with patch("sentry_sdk.capture_message", return_value="evt-1") as cap:
            app = create_app()
            client = TestClient(app)
            r = client.get("/health/sentry")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"
            assert data.get("event_id") == "evt-1"
            assert cap.called


def test_middleware_module_importable():
    from app.middleware.sentry_context import SentryContextMiddleware

    assert SentryContextMiddleware is not None
