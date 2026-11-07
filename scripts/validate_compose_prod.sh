#!/usr/bin/env bash
# Strict production compose validation for CI.
# Uses Docker Compose JSON output + Python stdlib json only (no PyYAML, no substring fallback).
# CI-only placeholder credentials — never real secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/docker-compose.prod.yml}"
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: missing $COMPOSE_FILE" >&2
  exit 1
fi

TMPDIR_CI="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_CI"' EXIT

ENV_FILE="$TMPDIR_CI/ci.env"
cat > "$ENV_FILE" <<'ENV'
# CI-only placeholders — not production credentials
SECRET_KEY=ci-compose-validation-secret-key-32b
ENVIRONMENT=production
ENV

export POSTGRES_USER=vrav
export POSTGRES_PASSWORD=ci-compose-test-password-not-real
export POSTGRES_DB=vrav
export VRV_ENV_FILE="$ENV_FILE"
export API_PUBLISH_PORT=8000

RENDERED_JSON="$TMPDIR_CI/rendered.json"
echo "== docker compose config --format json (strict) =="
docker compose \
  -f "$COMPOSE_FILE" \
  --env-file "$ENV_FILE" \
  config --format json > "$RENDERED_JSON"

echo "== structural checks (Python json only) =="
python3 - "$RENDERED_JSON" "$ROOT" "$COMPOSE_FILE" <<'PY'
import json
import sys
from pathlib import Path

rendered_path = Path(sys.argv[1])
repo_root = Path(sys.argv[2])
compose_file = Path(sys.argv[3])

raw = rendered_path.read_text()
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    raise SystemExit(f"FAIL: docker compose config did not produce valid JSON: {e}") from e

if not isinstance(data, dict):
    raise SystemExit(f"FAIL: expected JSON object, got {type(data).__name__}")

services = data.get("services")
if not isinstance(services, dict):
    raise SystemExit("FAIL: rendered config missing services object")

required = {"postgres", "redis", "api", "worker", "beat"}
missing = required - set(services)
if missing:
    raise SystemExit(f"FAIL: missing services: {sorted(missing)}")

def env_map(svc: dict) -> dict:
    env = svc.get("environment") or {}
    if isinstance(env, dict):
        return {str(k): str(v) if v is not None else "" for k, v in env.items()}
    if isinstance(env, list):
        out = {}
        for item in env:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
            elif isinstance(item, dict):
                for k, v in item.items():
                    out[str(k)] = str(v) if v is not None else ""
        return out
    raise SystemExit(f"FAIL: unexpected environment type: {type(env).__name__}")

def volumes_text(svc: dict) -> str:
    vols = svc.get("volumes") or []
    parts = []
    for v in vols:
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            parts.append(json.dumps(v, sort_keys=True))
        else:
            parts.append(str(v))
    return " ".join(parts)

def require_build(svc: dict, name: str, expected_dockerfile: str) -> None:
    build = svc.get("build")
    if not isinstance(build, dict):
        raise SystemExit(f"FAIL: {name} missing build object")
    dockerfile = build.get("dockerfile") or ""
    if expected_dockerfile not in str(dockerfile):
        raise SystemExit(
            f"FAIL: {name} dockerfile={dockerfile!r}, expected to contain {expected_dockerfile!r}"
        )
    context = str(build.get("context") or "")
    if not context:
        raise SystemExit(f"FAIL: {name} missing build.context")

for name in ("api", "worker"):
    svc = services[name]
    env = env_map(svc)
    path_val = env.get("LOCAL_STORAGE_PATH")
    if path_val != "/data/storage":
        raise SystemExit(f"FAIL: {name} LOCAL_STORAGE_PATH={path_val!r}, expected '/data/storage'")
    vol_s = volumes_text(svc)
    if "/data/storage" not in vol_s:
        raise SystemExit(f"FAIL: {name} volumes do not mount /data/storage: {vol_s!r}")

require_build(services["api"], "api", "Dockerfile.api")
require_build(services["worker"], "worker", "Dockerfile.worker")
require_build(services["beat"], "beat", "Dockerfile.worker")

for name in ("postgres", "redis"):
    hc = services[name].get("healthcheck")
    if not hc:
        raise SystemExit(f"FAIL: {name} missing healthcheck")

compose_dir = compose_file.parent
for rel in ("Dockerfile.api", "Dockerfile.worker"):
    p = compose_dir / rel
    if not p.is_file():
        raise SystemExit(f"FAIL: missing Dockerfile at {p}")

print("COMPOSE_STRUCTURE_OK", sorted(services.keys()))
print("COMPOSE_PROD_VALIDATION_PASS")
PY
