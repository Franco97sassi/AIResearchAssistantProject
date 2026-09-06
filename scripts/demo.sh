#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
PDF_PATH="${1:-Guia.pdf}"
QUESTION="${2:-Cual es la idea principal del documento?}"

if [[ ! -f "$PDF_PATH" ]]; then
  echo "No existe el PDF: $PDF_PATH" >&2
  echo "Uso: ./scripts/demo.sh [ruta.pdf] [pregunta]" >&2
  exit 1
fi

echo "1/3 Comprobando el backend..."
curl --fail --silent --show-error "$API_URL/health"
printf '\n\n'

echo "2/3 Subiendo e indexando $PDF_PATH..."
upload_response="$(
  curl --fail --silent --show-error \
    -X POST "$API_URL/upload-pdf" \
    -F "file=@${PDF_PATH};type=application/pdf"
)"
echo "$upload_response"
document_id="$(python -c 'import json,sys; print(json.load(sys.stdin)["document_id"])' <<<"$upload_response")"
printf '\n'

echo "3/3 Preguntando al agente sobre el documento $document_id..."
curl --fail --silent --show-error \
  -X POST "$API_URL/agent/chat" \
  -H "Content-Type: application/json" \
  -d "$(
    QUESTION="$QUESTION" DOCUMENT_ID="$document_id" python -c \
      'import json,os; print(json.dumps({"question": os.environ["QUESTION"], "session_id": "demo-cli", "document_id": os.environ["DOCUMENT_ID"], "limit": 4}))'
  )"
printf '\n'
