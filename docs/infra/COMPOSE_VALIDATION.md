# Production Compose Validation

CI runs `scripts/validate_compose_prod.sh` which:

1. Supplies **non-production** placeholder credentials (`POSTGRES_PASSWORD`, temp `VRV_ENV_FILE`).
2. Executes `docker compose … config` **without** ignoring errors.
3. Asserts required services: `api`, `worker`, `beat`, `redis`, `postgres`.
4. Asserts `LOCAL_STORAGE_PATH=/data/storage` and shared volume mount for API/Worker.
5. Asserts Dockerfiles exist and are referenced by the compose file.

Never commit real production secrets for this check.
