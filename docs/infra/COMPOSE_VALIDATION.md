# Production Compose Validation

CI runs:

1. `scripts/validate_compose_prod.sh` — **strict** `docker compose config --format json` + Python `json` only.
2. `scripts/test_validate_compose_prod_negative.sh` — invalid configs must exit non-zero.

## Positive checks
- CI-only placeholder credentials (`POSTGRES_PASSWORD`, temp `VRV_ENV_FILE`).
- Services: `postgres`, `redis`, `api`, `worker`, `beat`.
- `LOCAL_STORAGE_PATH=/data/storage` on API and Worker.
- Shared volume mount at `/data/storage`.
- Healthchecks on Postgres and Redis.
- API builds from `Dockerfile.api`; Worker and Beat from `Dockerfile.worker`.
- Dockerfile files exist under `infra/docker/`.

## No fallback
Structural validation uses `json.loads` only. There is no PyYAML soft path and no substring-only success path when JSON is invalid.

Never commit real production secrets for this check.
