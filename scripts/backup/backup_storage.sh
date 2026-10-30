#!/usr/bin/env bash
# Backup local storage directory or sync S3 bucket (aws cli).
set -euo pipefail
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR="${BACKUP_DIR:-./backups}/storage"
mkdir -p "$OUT_DIR"

if [[ "${STORAGE_BACKEND:-local}" == "local" ]]; then
  SRC="${LOCAL_STORAGE_PATH:-./data/storage}"
  TAR="$OUT_DIR/storage_${STAMP}.tar.gz"
  tar -czf "$TAR" -C "$(dirname "$SRC")" "$(basename "$SRC")"
  echo "OK $TAR"
else
  DEST="$OUT_DIR/s3_${STAMP}"
  mkdir -p "$DEST"
  aws s3 sync "s3://${S3_BUCKET:-vrav}" "$DEST" --endpoint-url "${S3_ENDPOINT:-}"
  echo "OK $DEST"
fi
