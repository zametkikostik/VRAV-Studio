#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="$OUT_DIR/vrav_${STAMP}.dump"

if [[ -n "${DATABASE_URL_SYNC:-}" ]]; then
  pg_dump --format=custom --no-owner --no-acl -f "$FILE" "$DATABASE_URL_SYNC"
elif [[ -n "${DATABASE_URL:-}" ]]; then
  URL="${DATABASE_URL/postgresql+asyncpg/postgresql}"
  pg_dump --format=custom --no-owner --no-acl -f "$FILE" "$URL"
else
  pg_dump --format=custom --no-owner --no-acl \
    -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" \
    -U "${PGUSER:-vrav}" -d "${PGDATABASE:-vrav}" -f "$FILE"
fi

sha256sum "$FILE" > "${FILE}.sha256" 2>/dev/null || shasum -a 256 "$FILE" > "${FILE}.sha256"
echo "OK $FILE"
KEEP="${BACKUP_KEEP:-14}"
ls -1t "$OUT_DIR"/vrav_*.dump 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
