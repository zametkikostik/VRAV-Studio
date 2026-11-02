"""Unified Redis access: standalone, Sentinel, or Cluster.

Env:
  REDIS_URL              — standalone (default redis://localhost:6379/0)
  REDIS_MODE             — standalone | sentinel | cluster  (default: standalone)
  REDIS_PASSWORD         — optional auth password
  REDIS_SENTINEL_HOSTS   — host1:26379,host2:26379 (required for sentinel)
  REDIS_SENTINEL_SERVICE — master name (default: mymaster)
  REDIS_CLUSTER_NODES    — host1:6379,host2:6379 (required for cluster)

Celery broker should keep using a single logical URL (standalone or
Sentinel-aware URL). Rate limiting / cache may use cluster when configured.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("vrav.redis")


def _password() -> str | None:
    p = (os.getenv("REDIS_PASSWORD") or "").strip()
    return p or None


def parse_host_port(spec: str, default_port: int) -> tuple[str, int]:
    spec = spec.strip()
    if not spec:
        raise ValueError("empty host:port")
    if ":" in spec:
        host, _, port_s = spec.rpartition(":")
        return host.strip(), int(port_s)
    return spec, default_port


def parse_node_list(raw: str, default_port: int) -> list[tuple[str, int]]:
    nodes: list[tuple[str, int]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        nodes.append(parse_host_port(part, default_port))
    return nodes


def redis_mode() -> str:
    return (os.getenv("REDIS_MODE") or "standalone").strip().lower()


@lru_cache
def get_redis_sync() -> Any:
    """Synchronous redis client suitable for health checks and limiters."""
    mode = redis_mode()
    password = _password()

    if mode == "cluster":
        from redis.cluster import RedisCluster

        nodes = parse_node_list(os.getenv("REDIS_CLUSTER_NODES", ""), 6379)
        if not nodes:
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 6379
            nodes = [(host, port)]
        startup = [{"host": h, "port": p} for h, p in nodes]
        return RedisCluster(
            startup_nodes=startup,
            password=password,
            decode_responses=True,
            skip_full_coverage_check=True,
        )

    if mode == "sentinel":
        from redis.sentinel import Sentinel

        hosts = parse_node_list(os.getenv("REDIS_SENTINEL_HOSTS", ""), 26379)
        if not hosts:
            raise RuntimeError("REDIS_SENTINEL_HOSTS required when REDIS_MODE=sentinel")
        service = os.getenv("REDIS_SENTINEL_SERVICE", "mymaster")
        sentinel = Sentinel(
            hosts,
            socket_connect_timeout=1.0,
            password=password,
        )
        return sentinel.master_for(
            service,
            password=password,
            decode_responses=True,
            db=int(os.getenv("REDIS_DB", "0")),
        )

    import redis

    url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    return redis.from_url(url, password=password, decode_responses=True)


def get_redis_async():
    """Async redis client for FastAPI paths."""
    import redis.asyncio as aioredis

    mode = redis_mode()
    password = _password()
    if mode == "cluster":
        url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        logger.warning(
            "REDIS_MODE=cluster: async client uses REDIS_URL gateway %s",
            url,
        )
        return aioredis.from_url(url, password=password, decode_responses=True)

    if mode == "sentinel":
        try:
            from redis.asyncio.sentinel import Sentinel as AsyncSentinel

            hosts = parse_node_list(os.getenv("REDIS_SENTINEL_HOSTS", ""), 26379)
            if not hosts:
                raise RuntimeError("REDIS_SENTINEL_HOSTS required when REDIS_MODE=sentinel")
            service = os.getenv("REDIS_SENTINEL_SERVICE", "mymaster")
            sentinel = AsyncSentinel(hosts, password=password, socket_connect_timeout=1.0)
            return sentinel.master_for(
                service,
                password=password,
                decode_responses=True,
                db=int(os.getenv("REDIS_DB", "0")),
            )
        except Exception as e:
            logger.error("async sentinel init failed: %s; falling back to REDIS_URL", e)

    url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    return aioredis.from_url(url, password=password, decode_responses=True)


def ping_redis() -> str:
    """Return 'ok' or error token for health endpoints."""
    try:
        client = get_redis_sync()
        pong = client.ping()
        if pong is True or pong == "PONG":
            return "ok"
        return f"unexpected:{pong!r}"
    except Exception as e:
        return f"error:{e.__class__.__name__}"


def clear_redis_caches() -> None:
    """Test helper: drop cached clients."""
    get_redis_sync.cache_clear()
