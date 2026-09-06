# ADR 0001: Redis y RQ para trabajos PDF

- Estado: aceptada
- Fecha: 2026-09-06

## Contexto
OCR, extracción e indexación pueden superar el timeout HTTP y bloquear workers web.

## Decisión
Usar Redis como broker persistente y RQ como worker Python. La API almacena primero el PDF,
encola solamente identificadores y rutas confiables, y expone consulta de estado.

## Consecuencias
La API responde rápido y los workers escalan independientemente. Redis pasa a ser dependencia
operativa; se requieren AOF, vigilancia de cola, trabajos idempotentes y limpieza de fallos.
