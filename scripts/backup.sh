#!/usr/bin/env bash
set -euo pipefail
: "${BACKUP_DIR:=./backups}"
: "${RETENTION_DAYS:=30}"
: "${DATA_VOLUME:=airesearchassistantproject_staging_data}"
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
docker run --rm -v "$DATA_VOLUME:/data:ro" -v "$(realpath "$BACKUP_DIR"):/backup" alpine:3.22 \
  tar -czf "/backup/data-$stamp.tar.gz" -C /data .
sha256sum "$BACKUP_DIR/data-$stamp.tar.gz" > "$BACKUP_DIR/data-$stamp.tar.gz.sha256"
find "$BACKUP_DIR" -type f -mtime "+$RETENTION_DAYS" -delete
