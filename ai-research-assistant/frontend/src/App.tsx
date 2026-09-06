import { FormEvent, useEffect, useMemo, useState } from 'react';

import { ChatMessages } from './components/ChatMessages';
import { SourceList } from './components/SourceList';
import { usePersistentSession } from './hooks/usePersistentSession';
import { API_BASE_URL, parseApiError } from './lib/api';
import { formatBytes, formatDate, mapHistoryMessage } from './lib/format';
import type {
  AiTopicsResponse,
  ChatMode,
  ChatMessage,
  ChatResponse,
  ChatSessionResponse,
  EvaluationResponse,
  MetricsResponse,
  SearchResponse,
  SessionSummary,
  UploadResponse,
} from './types';

function App() {
  const { sessionId, selectSession, createSession } = usePersistentSession();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const activeDocumentId = uploadResult?.document_id ?? null;
  const [uploadError, setUploadError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [searchQuestion, setSearchQuestion] = useState('');
  const [searchLimit, setSearchLimit] = useState(4);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [question, setQuestion] = useState('');
  const [chatMode, setChatMode] = useState<ChatMode>('agent');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatError, setChatError] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [aiTopics, setAiTopics] = useState<AiTopicsResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [evaluationError, setEvaluationError] = useState('');
  const [isEvaluating, setIsEvaluating] = useState(false);

  const canAsk = useMemo(() => question.trim().length > 0 && !isAsking, [isAsking, question]);

  useEffect(() => {
    refreshSessions();
    refreshProjectStatus();
  }, []);

  useEffect(() => {
    async function loadSelectedSession() {
      setIsLoadingHistory(true);
      try {
        const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`);
        if (!response.ok) {
          throw new Error(await parseApiError(response));
        }

        const payload = (await response.json()) as ChatSessionResponse;
        setChatMessages(payload.messages.map(mapHistoryMessage));
      } catch {
        setChatMessages([]);
      } finally {
        setIsLoadingHistory(false);
      }
    }

    loadSelectedSession();
  }, [sessionId]);

  async function refreshProjectStatus() {
    try {
      const [topicsResponse, metricsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/ai-topics`),
        fetch(`${API_BASE_URL}/metrics`),
      ]);

      if (topicsResponse.ok) {
        setAiTopics((await topicsResponse.json()) as AiTopicsResponse);
      }

      if (metricsResponse.ok) {
        setMetrics((await metricsResponse.json()) as MetricsResponse);
      }
    } catch {
      setAiTopics(null);
      setMetrics(null);
    }
  }

  async function refreshSessions() {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/sessions`);
      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const payload = (await response.json()) as { sessions: SessionSummary[] };
      setSessions(payload.sessions);
    } catch {
      setSessions([]);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError('');
    setUploadResult(null);

    if (!selectedFile) {
      setUploadError('Selecciona un archivo PDF antes de subirlo.');
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);
    setIsUploading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/upload-pdf`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const payload = (await response.json()) as UploadResponse;
      setUploadResult(payload);
      refreshProjectStatus();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'No se pudo subir el PDF.');
    } finally {
      setIsUploading(false);
    }
  }

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearchError('');
    setSearchResult(null);

    const normalizedQuestion = searchQuestion.trim();
    if (!normalizedQuestion) {
      setSearchError('Escribe una consulta para buscar fragmentos relevantes.');
      return;
    }

    setIsSearching(true);
    try {
      const params = new URLSearchParams({
        question: normalizedQuestion,
        limit: String(searchLimit),
      });
      if (activeDocumentId) {
        params.set('document_id', activeDocumentId);
      }
      const response = await fetch(`${API_BASE_URL}/search?${params.toString()}`);

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const payload = (await response.json()) as SearchResponse;
      setSearchResult(payload);
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : 'No se pudo ejecutar la busqueda.');
    } finally {
      setIsSearching(false);
    }
  }

  async function handleQuestionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setChatError('');

    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) {
      setChatError('Escribe una pregunta para consultar tus PDFs.');
      return;
    }

    setIsAsking(true);

    try {
      const chatEndpoint = chatMode === 'agent' ? '/agent/chat' : chatMode === 'stream' ? '/chat/stream' : '/chat';
      const response = await fetch(`${API_BASE_URL}${chatEndpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: normalizedQuestion,
          limit: 4,
          session_id: sessionId,
          document_id: activeDocumentId,
        }),
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      if (chatMode === 'stream' && response.body) {
        const optimisticId = crypto.randomUUID();
        const createdAt = new Date().toISOString();

        setChatMessages((messages) => [
          ...messages,
          {
            id: optimisticId,
            question: normalizedQuestion,
            answer: '',
            model: 'streaming',
            usedLlm: true,
            sources: [],
            agentSteps: [],
            createdAt,
          },
        ]);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split('\n\n');
          buffer = events.pop() ?? '';

          for (const eventBlock of events) {
            const dataLine = eventBlock.split('\n').find((line) => line.startsWith('data: '));
            if (!dataLine) continue;

            const data = JSON.parse(dataLine.slice(6));

            if ('token' in data) {
              setChatMessages((messages) =>
                messages.map((message) =>
                  message.id === optimisticId
                    ? { ...message, answer: message.answer + data.token }
                    : message,
                ),
              );
            }

            if ('session_id' in data) {
              selectSession(data.session_id);
              setChatMessages((messages) =>
                messages.map((message) =>
                  message.id === optimisticId
                    ? { ...message, model: data.model, sources: data.sources ?? [] }
                    : message,
                ),
              );
            }
          }
        }
      } else {
        const payload = (await response.json()) as ChatResponse;
        selectSession(payload.session_id);
        setChatMessages(payload.history.map(mapHistoryMessage));
      }

      setQuestion('');
      refreshSessions();
      refreshProjectStatus();
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'No se pudo responder la pregunta.');
    } finally {
      setIsAsking(false);
    }
  }

  async function handleEvaluateLastAnswer() {
    setEvaluationError('');
    setEvaluation(null);

    const lastMessage = chatMessages[chatMessages.length - 1];
    if (!lastMessage) {
      setEvaluationError('Haz una pregunta primero para evaluar la ultima respuesta.');
      return;
    }

    setIsEvaluating(true);
    try {
      const response = await fetch(`${API_BASE_URL}/evaluation/rag`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: lastMessage.question,
          answer: lastMessage.answer,
          sources: lastMessage.sources,
        }),
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const payload = (await response.json()) as EvaluationResponse;
      setEvaluation(payload);
    } catch (error) {
      setEvaluationError(error instanceof Error ? error.message : 'No se pudo evaluar la respuesta.');
    } finally {
      setIsEvaluating(false);
    }
  }

  function handleNewSession() {
    createSession();
    setChatMessages([]);
    setQuestion('');
    setChatError('');
  }

  function handleSelectSession(nextSessionId: string) {
    selectSession(nextSessionId);
    setChatError('');
  }

  return (
    <main className="app-shell">
      <section className="hero hero-copy-block">
        <div className="hero-content">
          <p className="eyebrow">Portfolio project · RAG Agent</p>
          <h1>Asistente IA para investigación documental</h1>
          <p className="hero-copy">
            Una experiencia pulida para demostrar carga de PDFs, búsqueda semántica,
            respuestas con fuentes, memoria conversacional, streaming y evaluación RAG.
          </p>
          <div className="hero-actions">
            <a className="primary-link" href="#chat-panel">Probar asistente</a>
            <span className="api-pill">Sesión {sessionId.slice(0, 8)}</span>
          </div>
        </div>

        <div className="portfolio-panel" aria-label="Resumen del proyecto">
          <div className="terminal-card">
            <span className="terminal-dot" />
            <span className="terminal-dot" />
            <span className="terminal-dot" />
            <p>pipeline.status</p>
            <strong>PDF → Chunks → Embeddings → ChromaDB → Agent</strong>
          </div>

          <div className="stat-grid">
            <div>
              <strong>{uploadResult?.chunks_indexed ?? '—'}</strong>
              <span>chunks indexados</span>
            </div>
            <div>
              <strong>{chatMessages.length}</strong>
              <span>mensajes</span>
            </div>
            <div>
              <strong>{metrics?.event_count ?? '—'}</strong>
              <span>eventos</span>
            </div>
          </div>
        </div>
      </section>

      <section className="workspace">
        <div className="tool-panel">
          <article className="card upload-card">
            <div className="card-heading">
              <span className="card-icon">PDF</span>
              <div>
                <h2>Base de conocimiento</h2>
                <p>Sube papers, apuntes o documentación. El backend extrae texto e indexa fragmentos consultables.</p>
              </div>
            </div>

            <form className="upload-form" onSubmit={handleUpload}>
              <label className="file-dropzone">
                <input
                  accept="application/pdf"
                  type="file"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                />
                <span>{selectedFile ? selectedFile.name : 'Selecciona o arrastra un PDF'}</span>
                {selectedFile && <small>{formatBytes(selectedFile.size)}</small>}
              </label>

              <button type="submit" disabled={isUploading}>
                {isUploading ? 'Indexando...' : 'Subir e indexar'}
              </button>
            </form>

            {uploadError && <p className="status error">{uploadError}</p>}
            {uploadResult && (
              <div className="status success">
                <strong>{uploadResult.message}</strong>
                <dl>
                  <div><dt>Archivo</dt><dd>{uploadResult.filename}</dd></div>
                  <div><dt>Tamaño</dt><dd>{formatBytes(uploadResult.size_bytes)}</dd></div>
                  <div><dt>Páginas</dt><dd>{uploadResult.page_count}</dd></div>
                  <div><dt>Caracteres</dt><dd>{uploadResult.character_count}</dd></div>
                  <div><dt>Chunks</dt><dd>{uploadResult.chunks_indexed}</dd></div>
                  <div><dt>Extracción</dt><dd>{uploadResult.extraction_method}</dd></div>
                </dl>
                <pre className="preview">{uploadResult.text_preview}</pre>
              </div>
            )}
          </article>

          <article className="card search-card">
            <div className="card-heading">
              <span className="card-icon">SRC</span>
              <div>
                <h2>Explorar evidencia</h2>
                <p>Inspecciona los fragmentos que recuperará el asistente antes de generar una respuesta.</p>
              </div>
            </div>

            <form className="search-form" onSubmit={handleSearchSubmit}>
              <textarea
                placeholder="Ejemplo: ¿Qué metodología usa el documento?"
                rows={3}
                value={searchQuestion}
                onChange={(event) => setSearchQuestion(event.target.value)}
              />

              <label className="limit-control">
                <span>Resultados</span>
                <input
                  max={10}
                  min={1}
                  type="number"
                  value={searchLimit}
                  onChange={(event) => setSearchLimit(Number(event.target.value))}
                />
              </label>

              <button type="submit" disabled={isSearching}>
                {isSearching ? 'Buscando...' : 'Buscar fuentes'}
              </button>
            </form>

            {searchError && <p className="status error">{searchError}</p>}
            {searchResult && (
              <div className="search-results">
                <p className="muted">
                  {searchResult.results.length} fuentes para: {searchResult.question}
                </p>
                <SourceList sources={searchResult.results} />
              </div>
            )}
          </article>
        </div>

        <article className="card chat-card" id="chat-panel">
          <div className="chat-header">
            <div>
              <p className="eyebrow">Demo interactiva</p>
              <h2>Preguntar al asistente</h2>
              <p>El modo agente ejecuta un grafo con roles de coordinación, búsqueda, crítica y citación.</p>
            </div>

            <button className="secondary-button" type="button" onClick={handleNewSession}>
              Nueva conversación
            </button>
          </div>

          <div className="mode-toggle" role="group" aria-label="Modo de chat">
            <button
              className={chatMode === 'agent' ? 'active' : ''}
              type="button"
              onClick={() => setChatMode('agent')}
            >
              Agente IA
            </button>

            <button
              className={chatMode === 'rag' ? 'active' : ''}
              type="button"
              onClick={() => setChatMode('rag')}
            >
              RAG clásico
            </button>

            <button
              className={chatMode === 'stream' ? 'active' : ''}
              type="button"
              onClick={() => setChatMode('stream')}
            >
              Streaming
            </button>
          </div>
          {activeDocumentId && (
            <p className="active-document-notice">
              Consultando solo el PDF activo: <strong>{uploadResult?.filename}</strong>
            </p>
          )}

          <form className="question-form" onSubmit={handleQuestionSubmit}>
            <textarea
              placeholder="Ejemplo: Resume el documento y cita las páginas más relevantes."
              rows={4}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />

            <button type="submit" disabled={!canAsk}>
              {isAsking ? 'Consultando...' : 'Enviar pregunta'}
            </button>
          </form>

          {chatError && <p className="status error">{chatError}</p>}

          <div className="messages" aria-live="polite">
            <ChatMessages messages={chatMessages} />
          </div>
        </article>

        <aside className="history-rail">
          <div className="rail-heading">
            <h2>Panel de control</h2>
            <p>Métricas, evaluación e historial para mostrar el proyecto de forma profesional.</p>
          </div>

          {aiTopics && (
            <div className="topic-cloud">
              {aiTopics.covered.slice(0, 10).map((topic) => (
                <span key={topic}>{topic}</span>
              ))}
            </div>
          )}

          {metrics && (
            <dl className="metrics-grid">
              <div>
                <dt>Eventos</dt>
                <dd>{metrics.event_count}</dd>
              </div>
              <div>
                <dt>Latencia</dt>
                <dd>{metrics.average_latency_ms} ms</dd>
              </div>
              <div>
                <dt>Tokens</dt>
                <dd>{metrics.total_estimated_tokens}</dd>
              </div>
              <div>
                <dt>Fuentes</dt>
                <dd>{metrics.average_source_count}</dd>
              </div>
            </dl>
          )}

          <button className="secondary-button full-width" type="button" onClick={refreshProjectStatus}>
            Actualizar métricas y temas
          </button>

          <button
            className="secondary-button full-width"
            type="button"
            onClick={handleEvaluateLastAnswer}
            disabled={isEvaluating}
          >
            {isEvaluating ? 'Evaluando...' : 'Evaluar última respuesta'}
          </button>

          {evaluationError && <p className="status error">{evaluationError}</p>}
          {evaluation && (
            <div className="evaluation-panel">
              <strong>Evaluación RAG</strong>
              <span>Faithfulness: {evaluation.faithfulness}</span>
              <span>Precisión contexto: {evaluation.context_precision}</span>
              <span>Cobertura fuentes: {evaluation.source_coverage}</span>
              <span>Riesgo: {evaluation.hallucination_risk}</span>
              <span>{evaluation.grounded ? 'Respuesta grounded' : 'Revisar grounding'}</span>
            </div>
          )}

          <div className="session-list">
            {isLoadingHistory && <p className="muted">Cargando historial...</p>}
            {sessions.length === 0 ? (
              <p className="muted">Sin conversaciones guardadas.</p>
            ) : (
              sessions.map((session) => (
                <button
                  className={`session-button ${session.session_id === sessionId ? 'active' : ''}`}
                  key={session.session_id}
                  type="button"
                  onClick={() => handleSelectSession(session.session_id)}
                >
                  <strong>{session.last_question || 'Conversación sin título'}</strong>
                  <span>{session.message_count} mensajes · {formatDate(session.updated_at)}</span>
                </button>
              ))
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}

export default App;
