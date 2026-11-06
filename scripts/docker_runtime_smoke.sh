#!/usr/bin/env bash
# Real Docker + Redis + Celery runtime smoke for API/Worker images.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_IMG="${API_IMG:-vrav-api:ci}"
WORKER_IMG="${WORKER_IMG:-vrav-worker:ci}"
NET="${NET:-vrav-ci-net}"
REDIS_C="${REDIS_C:-vrav-ci-redis}"
WORKER_C="${WORKER_C:-vrav-ci-worker}"

cleanup() {
  docker rm -f "$WORKER_C" "$REDIS_C" 2>/dev/null || true
  docker network rm "$NET" 2>/dev/null || true
}
trap cleanup EXIT

echo "== Build API =="
docker build -f infra/docker/Dockerfile.api -t "$API_IMG" .

echo "== Build Worker =="
docker build -f infra/docker/Dockerfile.worker -t "$WORKER_IMG" .

echo "== API import smoke =="
docker run --rm "$API_IMG" python -c "
from app.main import app
from worker.celery_app import celery_app
assert app is not None
assert celery_app is not None
print('API_IMPORT_OK')
"

echo "== Worker registry smoke =="
docker run --rm "$WORKER_IMG" python -c "
import sqlalchemy
import asyncpg
from worker.celery_app import celery_app
import worker.tasks  # noqa: F401
required = {
    'vrav.ping',
    'vrav.media.probe',
    'vrav.media.analyze',
    'vrav.media.transcribe',
    'vrav.media.render',
    'vrav.credits.release_stale',
    'vrav.gdpr.purge',
}
registered = set(celery_app.tasks.keys())
missing = required - registered
assert not missing, missing
print('WORKER_REGISTRY_OK', sorted(required))
"

echo "== Shared volume + Redis/Celery ping =="
docker network create "$NET"
docker run -d --name "$REDIS_C" --network "$NET" redis:7-alpine
for i in $(seq 1 30); do
  if docker exec "$REDIS_C" redis-cli ping | grep -q PONG; then break; fi
  sleep 1
done
docker exec "$REDIS_C" redis-cli ping | grep -q PONG

VOL=vrav_ci_storage_$$
docker volume create "$VOL" >/dev/null

docker run -d --name "$WORKER_C" --network "$NET" \
  -e REDIS_URL=redis://$REDIS_C:6379/0 \
  -e LOCAL_STORAGE_PATH=/data/storage \
  -v "$VOL":/data/storage \
  "$WORKER_IMG"

docker run --rm --network "$NET" \
  -e LOCAL_STORAGE_PATH=/data/storage \
  -v "$VOL":/data/storage \
  "$API_IMG" sh -c 'mkdir -p /data/storage && echo shared-ok > /data/storage/ci_marker.txt && test -f /data/storage/ci_marker.txt'

docker exec "$WORKER_C" sh -c 'test -f /data/storage/ci_marker.txt && grep -q shared-ok /data/storage/ci_marker.txt'
echo "SHARED_VOLUME_OK"

sleep 3
docker run --rm --network "$NET" \
  -e REDIS_URL=redis://$REDIS_C:6379/0 \
  "$API_IMG" python -c "
from worker.celery_app import celery_app
async_result = celery_app.send_task('vrav.ping')
result = async_result.get(timeout=30)
assert result and result.get('ok') is True, result
print('CELERY_PING_OK', result)
"

docker run --rm -v "$VOL":/data/storage "$API_IMG" sh -c 'rm -f /data/storage/ci_marker.txt' || true
docker volume rm "$VOL" >/dev/null || true

echo "DOCKER_RUNTIME_SMOKE_PASS"
