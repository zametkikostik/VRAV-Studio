#!/usr/bin/env bash
# Strict production compose validation for CI.
# Docker Compose JSON + Python stdlib json only.
# Dockerfile/context paths resolve relative to repository root (not temp COMPOSE_FILE parent).
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
repo_root = Path(sys.argv[2]).resolve()
compose_file = Path(sys.argv[3]).resolve()

EXPECTED_API_DOCKERFILE = (repo_root / "infra" / "docker" / "Dockerfile.api").resolve()
EXPECTED_WORKER_DOCKERFILE = (repo_root / "infra" / "docker" / "Dockerfile.worker").resolve()
EXPECTED_CONTEXT = repo_root.resolve()

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

def resolve_context(build: dict, compose_path: Path) -> Path:
    context = build.get("context")
    if not context:
        raise SystemExit("FAIL: build.context missing")
    p = Path(str(context))
    if p.is_absolute():
        return p.resolve()
    return (compose_path.parent / p).resolve()

def resolve_dockerfile(build: dict, compose_path: Path) -> Path:
    dockerfile = build.get("dockerfile")
    if not dockerfile:
        raise SystemExit("FAIL: build.dockerfile missing")
    p = Path(str(dockerfile))
    if p.is_absolute():
        return p.resolve()
    context = build.get("context")
    if context:
        ctx = Path(str(context))
        if not ctx.is_absolute():
            ctx = (compose_path.parent / ctx).resolve()
        else:
            ctx = ctx.resolve()
        return (ctx / p).resolve()
    return (compose_path.parent / p).resolve()

def require_build(svc: dict, name: str, expected_dockerfile: Path) -> None:
    build = svc.get("build")
    if not isinstance(build, dict):
        raise SystemExit(f"FAIL: {name} missing build object")

    ctx = resolve_context(build, compose_file)
    if ctx != EXPECTED_CONTEXT:
        raise SystemExit(
            f"FAIL: {name} build.context resolves to {ctx}, expected {EXPECTED_CONTEXT}"
        )

    df = resolve_dockerfile(build, compose_file)
    if df != expected_dockerfile:
        raise SystemExit(
            f"FAIL: {name} dockerfile resolves to {df}, expected {expected_dockerfile}"
        )
    if not expected_dockerfile.is_file():
        raise SystemExit(f"FAIL: expected Dockerfile does not exist: {expected_dockerfile}")
    if not df.is_file():
        raise SystemExit(f"FAIL: referenced Dockerfile does not exist: {df}")

for name in ("api", "worker"):
    svc = services[name]
    env = env_map(svc)
    path_val = env.get("LOCAL_STORAGE_PATH")
    if path_val != "/data/storage":
        raise SystemExit(f"FAIL: {name} LOCAL_STORAGE_PATH={path_val!r}, expected '/data/storage'")
    vol_s = volumes_text(svc)
    if "/data/storage" not in vol_s:
        raise SystemExit(f"FAIL: {name} volumes do not mount /data/storage: {vol_s!r}")

require_build(services["api"], "api", EXPECTED_API_DOCKERFILE)
require_build(services["worker"], "worker", EXPECTED_WORKER_DOCKERFILE)
require_build(services["beat"], "beat", EXPECTED_WORKER_DOCKERFILE)

for name in ("postgres", "redis"):
    hc = services[name].get("healthcheck")
    if not hc:
        raise SystemExit(f"FAIL: {name} missing healthcheck")

for expected in (EXPECTED_API_DOCKERFILE, EXPECTED_WORKER_DOCKERFILE):
    if not expected.is_file():
        raise SystemExit(f"FAIL: missing canonical Dockerfile at {expected}")

print("COMPOSE_STRUCTURE_OK", sorted(services.keys()))
print("COMPOSE_PROD_VALIDATION_PASS")
PY
