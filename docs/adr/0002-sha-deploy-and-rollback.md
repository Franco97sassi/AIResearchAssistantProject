# ADR 0002: despliegues inmutables por SHA con rollback

- Estado: aceptada
- Fecha: 2026-09-06

## Contexto
Etiquetas mutables y despliegues manuales dificultan reproducir y revertir una versión.

## Decisión
Publicar backend y frontend con el SHA del commit solo después de superar CI y la puerta de
calidad. Desplegar en serie, comprobar salud y restaurar automáticamente el SHA anterior si la
nueva versión no responde.

## Consecuencias
Cada release es trazable y el rollback es rápido. El health check no detecta degradaciones
semánticas posteriores; alertas y evaluación continua siguen siendo necesarias.
