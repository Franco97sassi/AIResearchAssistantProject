# Guion de demo (75–85 segundos)

Este guion permite grabar una demo corta con cualquier capturador de pantalla. Antes de grabar,
ejecuta `docker compose up --build`, abre `http://localhost:8080`, carga `Guia.pdf` y limpia la
sesión para que la indexación y las respuestas puedan mostrarse sin esperas inesperadas.

| Tiempo | Pantalla | Narración sugerida |
| --- | --- | --- |
| 0–8 s | Título y aplicación | “AI Research Assistant convierte PDFs en conocimiento consultable con evidencia verificable.” |
| 8–20 s | Subida de PDF | “Extrae texto u OCR, crea chunks y envía la indexación larga a Redis y RQ.” |
| 20–38 s | Pregunta y respuesta | “El pipeline recupera contexto desde ChromaDB y responde señalando archivo y página.” |
| 38–50 s | Fuentes desplegadas | “Cada fragmento conserva metadatos y distancia para que la respuesta se pueda auditar.” |
| 50–63 s | Pasos del agente | “LangGraph coordina búsqueda, crítica del contexto, redacción y verificación de citas.” |
| 63–75 s | Métricas y arquitectura | “La solución incluye evaluación RAG, aislamiento por tenant, trazas, Prometheus y CI/CD con rollback.” |
| 75–85 s | Repositorio | “El repositorio contiene Docker Compose, pruebas, benchmark reproducible, runbook y ADRs.” |

## Checklist de publicación

- Exportar en 1080p, sin documentos privados, claves, terminales con secretos ni datos personales.
- Mantener el cursor quieto durante las respuestas y ampliar las fuentes antes de mostrar métricas.
- Añadir subtítulos y un enlace corto al repositorio y a la demo, si existe un host activo.
- No afirmar que el entorno es “producción” ni “público” hasta verificar HTTPS, persistencia,
  autenticación, límites de uso y monitorización del host real.
