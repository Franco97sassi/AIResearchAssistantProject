#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 ]] || { echo "Uso: $0 backup.tar.gz" >&2; exit 2; }
: "${DATA_VOLUME:=airesearchassistantproject_staging_data}"
sha256sum -c "$1.sha256"
docker run --rm -v "$DATA_VOLUME:/data" -v "$(dirname "$(realpath "$1")"):/backup:ro" alpine:3.22 \
  sh -c "rm -rf /data/* && tar -xzf '/backup/$(basename "$1")' -C /data"
