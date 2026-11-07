#!/usr/bin/env bash
# Negative cases: invalid compose must fail with a *specific* error reason.
# Fixtures use absolute build context (= repo root) so path resolution is not
# polluted by placing the Compose file under /tmp.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VALIDATOR="$ROOT/scripts/validate_compose_prod.sh"
BASE="$ROOT/infra/docker/docker-compose.prod.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

normalize_context() {
  python3 - "$1" "$2" "$ROOT" <<'PY'
from pathlib import Path
import sys
src, dst, root = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]).resolve()
text = src.read_text()
text = text.replace("context: ../..", f"context: {root}")
dst.write_text(text)
PY
}

fail_case() {
  local name="$1"
  local file="$2"
  local expect_re="$3"
  echo "== negative case: $name =="
  local out rc
  set +e
  out="$(COMPOSE_FILE="$file" bash "$VALIDATOR" 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    echo "FAIL: expected non-zero exit for $name" >&2
    echo "$out" >&2
    exit 1
  fi
  if ! echo "$out" | grep -Eiq "$expect_re"; then
    echo "FAIL: $name failed for unexpected reason (wanted /$expect_re/)" >&2
    echo "----- output -----" >&2
    echo "$out" >&2
    exit 1
  fi
  echo "OK: $name failed as expected ($expect_re)"
}

normalize_context "$BASE" "$TMP/base.yml"

# 1) Missing worker — keep Compose dependency graph valid so docker compose
#    config succeeds and the *structural* validator reports the missing service.
python3 - "$TMP/base.yml" "$TMP/missing_worker.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
text = src.read_text()
text = text.replace("\n  worker:\n", "\n  worker_removed:\n", 1)
# beat: depends_on: [worker] short syntax in prod compose
text = text.replace(
    "    depends_on:\n      - worker\n",
    "    depends_on: []\n",
    1,
)
dst.write_text(text)
PY
fail_case "missing_worker" "$TMP/missing_worker.yml" "missing services:.*worker"

python3 - "$TMP/base.yml" "$TMP/bad_path.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.write_text(src.read_text().replace(
    "LOCAL_STORAGE_PATH: /data/storage",
    "LOCAL_STORAGE_PATH: /wrong/path",
))
PY
fail_case "wrong_storage_path" "$TMP/bad_path.yml" "LOCAL_STORAGE_PATH=.*/wrong/path"

echo "services: [" > "$TMP/broken.yml"
fail_case "broken_yaml" "$TMP/broken.yml" "(yaml|json|error|invalid|failed|while parsing)"

python3 - "$TMP/base.yml" "$TMP/bad_api_dockerfile.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.write_text(src.read_text().replace(
    "dockerfile: infra/docker/Dockerfile.api",
    "dockerfile: infra/docker/Dockerfile.api.MISSING",
    1,
))
PY
fail_case "incorrect_api_dockerfile" "$TMP/bad_api_dockerfile.yml" \
  "(api dockerfile resolves to|referenced Dockerfile does not exist).*Dockerfile\\.api\\.MISSING"

python3 - "$TMP/base.yml" "$TMP/bad_worker_dockerfile.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.write_text(src.read_text().replace(
    "dockerfile: infra/docker/Dockerfile.worker",
    "dockerfile: infra/docker/Dockerfile.worker.WRONG",
    1,
))
PY
fail_case "incorrect_worker_dockerfile" "$TMP/bad_worker_dockerfile.yml" \
  "(worker dockerfile resolves to|referenced Dockerfile does not exist).*Dockerfile\\.worker\\.WRONG"

python3 - "$TMP/base.yml" "$TMP/bad_context.yml" "$ROOT" <<'PY'
from pathlib import Path
import sys
src, dst, root = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]).resolve()
text = src.read_text()
needle = f"context: {root}"
text = text.replace(needle, "context: /tmp", 1)
dst.write_text(text)
PY
fail_case "incorrect_build_context" "$TMP/bad_context.yml" "api build.context resolves to"

python3 - "$TMP/base.yml" "$TMP/missing_api_df.yml" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.write_text(src.read_text().replace(
    "dockerfile: infra/docker/Dockerfile.api",
    "dockerfile: infra/docker/DoesNotExist.api",
    1,
))
PY
fail_case "missing_api_dockerfile" "$TMP/missing_api_df.yml" \
  "(api dockerfile resolves to|referenced Dockerfile does not exist).*DoesNotExist\\.api"

echo "ALL_NEGATIVE_CASES_PASS"
