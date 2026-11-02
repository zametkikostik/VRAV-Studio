"""Iteration 6 Part 2: Redis client factory (standalone / sentinel / cluster parsing)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.redis_client import (
    clear_redis_caches,
    parse_host_port,
    parse_node_list,
    ping_redis,
    redis_mode,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_redis_caches()
    yield
    clear_redis_caches()


def test_parse_host_port():
    assert parse_host_port("redis.internal:6380", 6379) == ("redis.internal", 6380)
    assert parse_host_port("localhost", 26379) == ("localhost", 26379)


def test_parse_node_list():
    nodes = parse_node_list("a:1, b:2, c", 6379)
    assert nodes == [("a", 1), ("b", 2), ("c", 6379)]


def test_redis_mode_default(monkeypatch):
    monkeypatch.delenv("REDIS_MODE", raising=False)
    assert redis_mode() == "standalone"


def test_ping_redis_skipped_path(monkeypatch):
    monkeypatch.setenv("REDIS_MODE", "standalone")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    clear_redis_caches()
    status = ping_redis()
    assert status.startswith("error:") or status == "ok"


def test_get_redis_sync_standalone(monkeypatch):
    monkeypatch.setenv("REDIS_MODE", "standalone")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    clear_redis_caches()
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    with patch("redis.from_url", return_value=mock_client) as fu:
        from app.core.redis_client import get_redis_sync

        clear_redis_caches()
        c = get_redis_sync()
        fu.assert_called()
        assert c is mock_client
        assert ping_redis() == "ok"


def test_parse_sentinel_hosts_required(monkeypatch):
    monkeypatch.setenv("REDIS_MODE", "sentinel")
    monkeypatch.delenv("REDIS_SENTINEL_HOSTS", raising=False)
    clear_redis_caches()
    with pytest.raises(Exception):
        from app.core.redis_client import get_redis_sync

        get_redis_sync()


def test_docs_and_compose_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    assert (root / "docs/architecture/REDIS.md").exists()
    assert (root / "infra/docker/docker-compose.redis-ha.yml").exists()
