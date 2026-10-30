#!/usr/bin/env bash
# Restore from pg_dump custom format. DESTRUCTIVE on target DB.
set -euo pipefail

FILE="${1:-}"
if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "Usage: $0 <backup.dump>" >&2
  exit 1
fi

if [[ -f "${FILE}.sha256" ]]; then
  sha256sum -c "${FILE}.sha256" 2>/dev/null || shasum -a 256 -c "${FILE}.sha256"
fi

TARGET="${DATABASE_URL_SYNC:-${DATABASE_URL:-}}"
TARGET="${TARGET/postgresql+asyncpg/postgresql}"

echo "WARNING: restoring into ${TARGET:-local default}"
read -r -p "Type RESTORE to continue: " CONFIRM
[[ "$CONFIRM" == "RESTORE" ]] || exit 1

if [[ -n "$TARGET" ]]; then
  pg_restore --clean --if-exists --no-owner --no-acl -d "$TARGET" "$FILE"
else
  pg_restore --clean --if-exists --no-owner --no-acl \
    -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" \
    -U "${PGUSER:-vrav}" -d "${PGDATABASE:-vrav}" "$FILE"
fi
echo "RESTORE OK"
