#!/usr/bin/env bash
# Negative cases: invalid compose must exit non-zero.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VALIDATOR="$ROOT/scripts/validate_compose_prod.sh"
BASE="$ROOT/infra/docker/docker-compose.prod.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail_case() {
  local name="$1"
  local file="$2"
  echo "== negative case: $name =="
  if COMPOSE_FILE="$file" bash "$VALIDATOR"; then
    echo "FAIL: expected non-zero exit for $name" >&2
    exit 1
  fi
  echo "OK: $name correctly failed"
}

python3 - "$BASE" "$TMP/missing_worker.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
text = src.read_text()
text = text.replace("\n  worker:\n", "\n  worker_removed:\n", 1)
dst.write_text(text)
PY
fail_case "missing_worker" "$TMP/missing_worker.yml"

python3 - "$BASE" "$TMP/bad_path.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.write_text(src.read_text().replace("LOCAL_STORAGE_PATH: /data/storage", "LOCAL_STORAGE_PATH: /wrong/path"))
PY
fail_case "wrong_storage_path" "$TMP/bad_path.yml"

echo "services: [" > "$TMP/broken.yml"
fail_case "broken_yaml" "$TMP/broken.yml"

python3 - "$BASE" "$TMP/bad_dockerfile.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.write_text(src.read_text().replace("dockerfile: infra/docker/Dockerfile.api", "dockerfile: infra/docker/Dockerfile.api.MISSING", 1))
PY
fail_case "missing_dockerfile_name" "$TMP/bad_dockerfile.yml"

echo "ALL_NEGATIVE_CASES_PASS"
