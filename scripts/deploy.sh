#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required}"
: "${DEPLOY_DIR:=/opt/ai-research-assistant}"
cd "$DEPLOY_DIR"
previous="$(cat .deployed-tag 2>/dev/null || true)"
printf '%s\n' "$IMAGE_TAG" > .candidate-tag
export IMAGE_TAG
compose=(docker compose -f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.deploy.yml)
"${compose[@]}" pull
"${compose[@]}" up -d --remove-orphans
if ! timeout 120 bash -c 'until curl -fsS http://localhost:8000/health; do sleep 3; done'; then
  echo "Health check failed; rolling back to $previous" >&2
  [[ -n "$previous" ]] || exit 1
  export IMAGE_TAG="$previous"
  "${compose[@]}" up -d --remove-orphans
  exit 1
fi
mv .candidate-tag .deployed-tag
