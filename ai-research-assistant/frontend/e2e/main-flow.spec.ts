import { expect, test } from '@playwright/test';

const source = {
  text: 'El reranking reordena los fragmentos recuperados antes de generar la respuesta.',
  filename: 'guia-rag-seguro.pdf',
  page_number: 1,
  distance: 0.12,
  document_id: 'demo-document',
};

test('sube un PDF, pregunta y muestra la fuente trazable', async ({ page }) => {
  await page.route('http://localhost:8000/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === '/upload-pdf') {
      await route.fulfill({
        json: {
          message: 'PDF indexado correctamente.',
          filename: 'guia-rag-seguro.pdf',
          size_bytes: 2048,
          page_count: 2,
          character_count: 950,
          chunks_indexed: 4,
          extraction_method: 'text',
          text_preview: source.text,
          document_id: source.document_id,
        },
      });
      return;
    }

    if (path === '/agent/chat') {
      const body = request.postDataJSON();
      expect(body.document_id).toBe(source.document_id);
      await route.fulfill({
        json: {
          session_id: body.session_id,
          answer: 'El reranking mejora el orden de la evidencia recuperada.',
          model: 'local-e2e',
          used_llm: false,
          sources: [source],
          agent_steps: [
            {
              name: 'retrieve',
              role: 'investigador',
              description: 'Recupera evidencia del PDF activo.',
              tool: 'search_similar_chunks',
              decision: 'contexto suficiente',
            },
          ],
          history: [
            {
              id: 'message-e2e',
              question: body.question,
              answer: 'El reranking mejora el orden de la evidencia recuperada.',
              model: 'local-e2e',
              used_llm: false,
              sources: [source],
              agent_steps: [
                {
                  name: 'retrieve',
                  role: 'investigador',
                  description: 'Recupera evidencia del PDF activo.',
                  tool: 'search_similar_chunks',
                  decision: 'contexto suficiente',
                },
              ],
              created_at: '2026-01-01T12:00:00Z',
            },
          ],
        },
      });
      return;
    }

    if (path.startsWith('/chat/sessions/')) {
      await route.fulfill({ json: { session_id: 'e2e-session', messages: [] } });
      return;
    }

    if (path === '/chat/sessions') {
      await route.fulfill({ json: { sessions: [] } });
      return;
    }

    if (path === '/ai-topics') {
      await route.fulfill({ json: { covered: [], pending: [] } });
      return;
    }

    if (path === '/metrics') {
      await route.fulfill({
        json: {
          event_count: 0,
          average_latency_ms: 0,
          total_estimated_tokens: 0,
          average_source_count: 0,
        },
      });
      return;
    }

    await route.fulfill({ status: 404, json: { detail: 'Ruta no simulada' } });
  });

  await page.goto('/');
  await page.getByLabel('Selecciona o arrastra un PDF').setInputFiles({
    name: 'guia-rag-seguro.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 fixture E2E'),
  });
  await page.getByRole('button', { name: 'Subir e indexar' }).click();

  await expect(page.getByText('PDF indexado correctamente.')).toBeVisible();
  await expect(page.getByText('Consultando solo el PDF activo:')).toContainText(
    'guia-rag-seguro.pdf',
  );

  await page
    .getByPlaceholder('Ejemplo: Resume el documento y cita las páginas más relevantes.')
    .fill('¿Para qué sirve el reranking?');
  await page.getByRole('button', { name: 'Enviar pregunta' }).click();

  await expect(page.getByText('El reranking mejora el orden de la evidencia recuperada.')).toBeVisible();
  await expect(page.getByText('guia-rag-seguro.pdf · pág. 1', { exact: true })).toBeVisible();
  await expect(page.getByText('Pasos del agente')).toBeVisible();
});
