# ADR 0003: observabilidad abierta y evaluación como puerta

- Estado: aceptada
- Fecha: 2026-09-06

## Contexto
Un RAG puede estar disponible y aun así degradar retrieval, latencia o coste.

## Decisión
Exponer métricas Prometheus desde el almacén local, provisionar Grafana y bloquear CI si ninguna
configuración consigue Hit Rate ≥ 0.90 y MRR ≥ 0.75 sobre el dataset versionado.

## Consecuencias
Los umbrales son visibles y reproducibles sin SaaS. La media de latencia local y el dataset
pequeño son una base inicial; producción deberá adoptar histogramas, ventanas y casos reales
anonimizados revisados por humanos.
