#!/usr/bin/env bash
# Strict production compose validation for CI.
# Uses non-production placeholder credentials only — never real secrets.
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

# Minimal env file so Compose env_file path resolves (no real secrets).
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

RENDERED="$TMPDIR_CI/rendered.yml"
echo "== docker compose config (strict) =="
docker compose \
  -f "$COMPOSE_FILE" \
  --env-file "$ENV_FILE" \
  config > "$RENDERED"

echo "== structural checks on rendered config =="
python3 - "$RENDERED" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
try:
    import yaml  # type: ignore
    data = yaml.safe_load(text)
except Exception:
    data = None

required_services = {"api", "worker", "beat", "redis", "postgres"}
if data is not None:
    services = set((data.get("services") or {}).keys())
    missing = required_services - services
    assert not missing, f"missing services: {missing}"
    for name in required_services:
        svc = data["services"][name]
        assert isinstance(svc, dict), name
    for name in ("api", "worker"):
        env = data["services"][name].get("environment") or {}
        if isinstance(env, list):
            env_map = {}
            for item in env:
                if isinstance(item, str) and "=" in item:
                    k, v = item.split("=", 1)
                    env_map[k] = v
            env = env_map
        path_val = env.get("LOCAL_STORAGE_PATH")
        assert path_val == "/data/storage", f"{name} LOCAL_STORAGE_PATH={path_val!r}"
        vols = data["services"][name].get("volumes") or []
        vol_s = " ".join(str(v) for v in vols)
        assert "/data/storage" in vol_s, f"{name} volumes missing /data/storage: {vols}"
    for name in ("postgres", "redis"):
        assert data["services"][name].get("healthcheck"), f"{name} missing healthcheck"
    for name in ("api", "worker", "beat"):
        build = data["services"][name].get("build") or {}
        assert build.get("dockerfile") or data["services"][name].get("image"), f"{name} missing build"
    print("COMPOSE_STRUCTURE_OK", sorted(services))
else:
    for svc in required_services:
        assert f"{svc}:" in text or f"  {svc}:" in text, f"service {svc} not in rendered config"
    assert "LOCAL_STORAGE_PATH: /data/storage" in text or "LOCAL_STORAGE_PATH=/data/storage" in text
    assert "/data/storage" in text
    assert "healthcheck:" in text
    print("COMPOSE_STRUCTURE_OK (string fallback)")
PY

grep -q 'dockerfile: infra/docker/Dockerfile.api' "$COMPOSE_FILE"
grep -q 'dockerfile: infra/docker/Dockerfile.worker' "$COMPOSE_FILE"
test -f infra/docker/Dockerfile.api
test -f infra/docker/Dockerfile.worker

echo "COMPOSE_PROD_VALIDATION_PASS"
