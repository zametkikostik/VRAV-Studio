# Production Compose Validation

CI runs:

1. `scripts/validate_compose_prod.sh` — `docker compose config --format json` + Python `json`.
2. `scripts/test_validate_compose_prod_negative.sh` — invalid configs must exit non-zero **with the expected error**.

## Path resolution
Dockerfile and build context paths are resolved against the **repository root** using Compose semantics (`context` + `dockerfile`). Validation does **not** require Dockerfiles to live next to temporary negative-test Compose files.

Expected:
- Context → repository root
- API Dockerfile → `infra/docker/Dockerfile.api`
- Worker / Beat Dockerfile → `infra/docker/Dockerfile.worker`
- `LOCAL_STORAGE_PATH=/data/storage` + mount

Never commit real production secrets for this check.
