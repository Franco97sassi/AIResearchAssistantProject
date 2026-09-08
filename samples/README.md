# PDFs seguros para la demo

El script de esta carpeta genera dos documentos pequeños y ficticios que no contienen datos
personales, secretos ni material de terceros. Los PDF generados se ignoran en Git para evitar
incluir archivos binarios en commits y pull requests.

## Generación

Después de instalar las dependencias del backend, ejecuta desde la raíz del repositorio:

```bash
python samples/generate_pdfs.py
```

El comando crea `guia-rag-seguro.pdf` e `informe-solar-ficticio.pdf` dentro de esta carpeta. Puedes
regenerarlos cuando los necesites y eliminarlos después de la entrevista sin afectar el repositorio.

## `guia-rag-seguro.pdf`

Nota técnica de dos páginas sobre retrieval, reranking y citas en un sistema RAG.

Preguntas sugeridas:

- ¿Qué problema resuelve el reranking?
- ¿Qué información debe incluir una cita trazable?
- ¿Qué métricas propone revisar la guía?

## `informe-solar-ficticio.pdf`

Informe ficticio de dos páginas sobre el proyecto solar imaginario «Aurora», con cifras inventadas
y una tabla sencilla para probar consultas numéricas.

Preguntas sugeridas:

- ¿Cuánta energía produjo Aurora en abril?
- ¿Qué acción se recomienda para el siguiente trimestre?
- ¿Cuál fue la disponibilidad media reportada?

> Todos los nombres y valores producidos por el script fueron creados exclusivamente como fixtures
> de demostración y no describen personas, organizaciones o instalaciones reales.
