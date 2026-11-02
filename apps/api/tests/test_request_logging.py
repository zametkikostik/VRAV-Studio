"""Iteration 6: request logging middleware + ApiRequestLog model."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_log import SKIP_PATHS, RequestLogMiddleware, persist_api_request_log
from app.models.api_log import ApiRequestLog


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/organizations")
    async def orgs():
        return [{"id": "1"}]

    @app.get("/boom")
    async def boom():
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="bad")

    app.add_middleware(RequestLogMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def test_health_not_persisted():
    client = _client()
    with patch(
        "app.middleware.request_log.persist_api_request_log", new_callable=AsyncMock
    ) as persist:
        r = client.get("/health")
        assert r.status_code == 200
        assert "X-Request-ID" in r.headers
        persist.assert_not_called()


def test_api_request_persisted_and_has_request_id():
    client = _client()
    with patch(
        "app.middleware.request_log.persist_api_request_log", new_callable=AsyncMock
    ) as persist:
        r = client.get("/organizations")
        assert r.status_code == 200
        assert "X-Request-ID" in r.headers
        assert len(r.headers["X-Request-ID"]) >= 8
        persist.assert_awaited()
        kwargs = persist.await_args.args[0]
        assert kwargs["method"] == "GET"
        assert kwargs["path"] == "/organizations"
        assert kwargs["status_code"] == 200
        assert kwargs["duration_ms"] >= 0
        assert kwargs["request_id"] == r.headers["X-Request-ID"]


def test_error_status_sets_error_message():
    client = _client()
    with patch(
        "app.middleware.request_log.persist_api_request_log", new_callable=AsyncMock
    ) as persist:
        r = client.get("/boom")
        assert r.status_code == 400
        kwargs = persist.await_args.args[0]
        assert kwargs["status_code"] == 400
        assert kwargs["error_message"] == "HTTP 400"


def test_skip_paths_include_health_and_metrics():
    assert "/health" in SKIP_PATHS
    assert "/metrics" in SKIP_PATHS


def test_model_and_migration_exist():
    root = Path(__file__).resolve().parents[3]
    assert (root / "apps/api/app/models/api_log.py").exists()
    mig = root / "infra/alembic/versions/013_api_request_logs.py"
    assert mig.exists()
    body = mig.read_text()
    assert 'down_revision = "012"' in body
    assert "api_request_logs" in body
    assert ApiRequestLog.__tablename__ == "api_request_logs"


@pytest.mark.asyncio
async def test_persist_swallows_db_errors():
    await persist_api_request_log(
        {
            "method": "GET",
            "path": "/x",
            "status_code": 200,
            "duration_ms": 1.0,
            "request_id": "abc",
        }
    )
