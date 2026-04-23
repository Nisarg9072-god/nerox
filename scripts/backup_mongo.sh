#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MONGO_URI:-}" ]]; then
  echo "MONGO_URI is required"
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-./backup}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_PATH="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "${OUT_PATH}"
mongodump --uri="${MONGO_URI}" --out="${OUT_PATH}"
echo "Mongo backup completed: ${OUT_PATH}"

