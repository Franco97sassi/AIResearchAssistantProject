# Operación, despliegue y recuperación

## Pipeline y rollback

Los pull requests ejecutan lint, tipos, cobertura, build web, evaluación RAG y pruebas
adversariales. Un CI correcto en `main` construye imágenes inmutables etiquetadas con el SHA,
las publica en GHCR y despliega por SSH. `scripts/deploy.sh` espera el health check durante 120
segundos y, si falla, vuelve al último SHA registrado. El entorno `production` de GitHub debe
requerir aprobación y contener `DEPLOY_HOST`, `DEPLOY_USER` y `DEPLOY_SSH_KEY`.

## Secretos

No se versionan `.env` ni archivos de `secrets/`. En producción use GitHub Environments para
secretos del pipeline y Docker Secrets, Vault o el gestor del proveedor para runtime. Las claves
de modelos aceptan `GROQ_API_KEY_FILE`, `OPENAI_API_KEY_FILE` y `ANTHROPIC_API_KEY_FILE`; el
archivo montado tiene precedencia sobre la variable. Rote claves trimestralmente y de inmediato
ante una exposición, aplique mínimo privilegio y nunca escriba valores en logs.

## Backups y retención

Programe diariamente `RETENTION_DAYS=30 scripts/backup.sh`. Genera un tar comprimido del volumen
persistente y su SHA-256, y elimina copias locales vencidas. Copie el resultado a almacenamiento
de objetos cifrado e inmutable con política: 30 diarios, 12 mensuales y 7 anuales. Ejecute una
restauración en staging con `scripts/restore.sh backups/data-….tar.gz` cada trimestre. Objetivos:
RPO 24 horas y RTO 2 horas. La restauración es destructiva y exige detener escrituras primero.

## Observabilidad, coste y carga

`docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d` levanta
Prometheus y Grafana. El dashboard muestra disponibilidad, latencia y coste estimado; las alertas
incluyen caída, latencia media superior a 2 s y gasto diario superior a USD 10. Configure precios
mediante `LLM_INPUT_COST_PER_MILLION` y `LLM_OUTPUT_COST_PER_MILLION`; son estimaciones, no
facturas. En producción proteja métricas en una red privada y conecte Alertmanager al canal de
guardia.

Ejecute carga en un entorno aislado: `k6 run -e BASE_URL=https://staging.example load/k6.js`.
El umbral falla con más de 1 % de errores o p95 superior a 1.5 s. No use datos reales ni ejecute
contra producción sin una ventana aprobada.

## Procesamiento asíncrono

`POST /jobs/upload-pdf` guarda el archivo y devuelve HTTP 202 con `job_id`. Un worker RQ consume
la cola Redis `pdf-indexing`; `GET /jobs/{job_id}` informa `queued`, `started`, `finished` o
`failed`. El endpoint síncrono original se conserva para compatibilidad. Redis usa AOF y los
archivos y Chroma comparten volúmenes entre API y worker.

## Runbook mínimo

1. Confirmar `/health`, Grafana, cola RQ y espacio de volúmenes.
2. Correlacionar la incidencia con `X-Trace-ID`; nunca copiar contenido privado al ticket.
3. Si un release falla, confirmar que `.deployed-tag` volvió al SHA anterior.
4. Si hay corrupción, detener API/worker, verificar checksum y restaurar la última copia válida.
5. Documentar tiempos, impacto, causa y acciones posteriores.
