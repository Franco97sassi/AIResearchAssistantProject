# Frontend React - Paso 8

Interfaz web para el AI Research Assistant. Permite subir PDFs al endpoint
`/upload-pdf`, hacer preguntas al endpoint `/chat`, revisar fuentes recuperadas
por RAG y mantener historial con memoria por sesion.

## Requisitos

- Node.js 20 o superior.
- Backend FastAPI ejecutandose en `http://localhost:8000`.

## Configuracion

1. Copia las variables de entorno:

   ```bash
   cp .env.example .env
   ```

2. Si tu API corre en otro host o puerto, ajusta:

   ```bash
   VITE_API_BASE_URL=http://localhost:8000
   ```

3. Instala dependencias:

   ```bash
   npm install
   ```

4. Inicia el frontend:

   ```bash
   npm run dev
   ```

5. Abre la app en:

   ```text
   http://localhost:5173
   ```

## Flujo de uso

1. Selecciona un PDF con texto seleccionable.
2. Pulsa **Subir e indexar PDF**.
3. Espera la confirmacion con paginas, chunks y vista previa del texto.
4. Escribe una pregunta sobre el PDF.
5. Haz preguntas de seguimiento: el backend usa la memoria de la sesion.
6. Revisa **Fuentes recuperadas** para validar el contexto usado.
7. Usa **Historial** para recuperar conversaciones previas o iniciar una nueva.
