# Redis topology (Iteration 6 Part 2)

## Modes

| `REDIS_MODE` | Use case | Client |
|--------------|----------|--------|
| `standalone` (default) | Dev, single VDS | `REDIS_URL` |
| `sentinel` | HA primary/replica | `REDIS_SENTINEL_HOSTS` + `REDIS_SENTINEL_SERVICE` |
| `cluster` | Sharded cache / rate-limit keys | `REDIS_CLUSTER_NODES` |

## Why Sentinel for Celery

Celery’s Redis broker expects a single logical master. **Redis Cluster is a poor fit
for the Celery broker.** Prefer:

- **Sentinel** (or managed Redis with failover) for broker + result backend
- Optional **Cluster** only for pure cache / rate-limit keyspace if needed later

## Local HA stack

```bash
docker compose -f infra/docker/docker-compose.redis-ha.yml up -d
```

App environment example:

```env
REDIS_MODE=sentinel
REDIS_SENTINEL_HOSTS=localhost:26379
REDIS_SENTINEL_SERVICE=mymaster
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_BACKEND=redis
ENVIRONMENT=production
```

## Production checklist

1. Set `RATE_LIMIT_BACKEND=redis` (no memory fallback).
2. Use Sentinel or managed Redis with automatic failover for Celery.
3. `/health/ready` reports `redis` + `redis_mode`.
4. Do not put secrets in compose files — use env / secret manager.

## Code entry points

- `app.core.redis_client.get_redis_sync` / `get_redis_async` / `ping_redis`
- `app.api.health.health_ready`
