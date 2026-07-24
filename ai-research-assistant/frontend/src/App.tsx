import { FormEvent, useEffect, useMemo, useState } from 'react';

type UploadResponse = {
  message: string;
  filename: string;
  stored_filename: string;
  size_bytes: number;
  page_count: number;
  character_count: number;
  extraction_method: string;
  ocr_attempted: boolean;
  ocr_available: boolean;
  text_preview: string;
  document_id: string;
  chunks_indexed: number;
  collection_name: string;
};

type InvoiceExtractionResponse = {
  filename: string;
  stored_filename: string;
  page_count: number;
  character_count: number;
  extraction_method: string;
  ocr_attempted: boolean;
  ocr_available: boolean;
  cliente: string;
  importe: number;
  moneda: string | null;
  fecha: string | null;
  numero_factura: string | null;
  confidence: number;
  missing_fields: string[];
  text_preview: string;
};

type Source = {
  text: string;
  filename: string;
  page_number: number;
  document_id: string;
  distance: number | null;
};

type AgentStep = {
  name: string;
  description: string;
  tool: string | null;
  decision: string | null;
};

type ChatHistoryMessage = {
  id: string;
  question: string;
  answer: string;
  model: string;
  used_llm: boolean;
  sources: Source[];
  agent_steps?: AgentStep[];
  created_at: string;
};

type ChatResponse = {
  session_id: string;
  question: string;
  answer: string;
  model: string;
  used_llm: boolean;
  sources: Source[];
  agent_steps?: AgentStep[];
  agent_framework?: string;
  history: ChatHistoryMessage[];
};

type ChatSessionResponse = {
  session_id: string;
  created_at: string;
  updated_at: string;
  messages: ChatHistoryMessage[];
};

type SessionSummary = {
  session_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_question: string;
};

type ChatMode = 'rag' | 'agent' | 'stream';

type ChatMessage = {
  id: string;
  question: string;
  answer: string;
  model: string;
  usedLlm: boolean;
  sources: Source[];
  agentSteps: AgentStep[];
  createdAt: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const SESSION_STORAGE_KEY = 'ai-research-assistant-session-id';

function createSessionId(): string {
  return crypto.randomUUID();
}

function getInitialSessionId(): string {
  const storedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
  if (storedSessionId) {
    return storedSessionId;
  }

  const sessionId = createSessionId();
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}

async function parseApiError(response: Response): Promise<string> {
  const fallback = `Error ${response.status}: ${response.statusText}`;

  try {
    const payload = await response.json();
    if (typeof payload.detail === 'string') {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item: { msg?: string }) => item.msg ?? JSON.stringify(item))
        .join(', ');
    }
  } catch {
    return fallback;
  }

  return fallback;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function formatDate(value: string): string {
  if (!value) return 'Sin fecha';
  return new Date(value).toLocaleString();
}

function formatDistance(value: number | null): string {
  if (value === null) return 'Sin distancia';
  return value.toFixed(4);
}

function mapHistoryMessage(message: ChatHistoryMessage): ChatMessage {
  return {
    id: message.id,
    question: message.question,
    answer: message.answer,
    model: message.model,
    usedLlm: message.used_llm,
    sources: message.sources,
    agentSteps: message.agent_steps ?? [],
    createdAt: message.created_at,
  };
}

function App() {
  const [sessionId, setSessionId] = useState(getInitialSessionId);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);
  const [invoiceResult, setInvoiceResult] = useState<InvoiceExtractionResponse | null>(null);
  const [invoiceError, setInvoiceError] = useState('');
  const [isExtractingInvoice, setIsExtractingInvoice] = useState(false);
  const [question, setQuestion] = useState('');
  const [chatMode, setChatMode] = useState<ChatMode>('agent');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatError, setChatError] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const canAsk = useMemo(() => question.trim().length > 0 && !isAsking, [isAsking, question]);

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

  useEffect(() => {
    let cancelled = false;

    async function loadSession() {
      setIsLoadingHistory(true);
      try {
        const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`);
        if (!response.ok) {
          throw new Error(await parseApiError(response));
        }

        const payload = (await response.json()) as ChatSessionResponse;
        if (!cancelled) {
          setChatMessages(payload.messages.map(mapHistoryMessage));
        }
      } catch {
        if (!cancelled) {
          setChatMessages([]);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingHistory(false);
        }
      }
    }

    loadSession();
    refreshSessions();

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

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
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'No se pudo subir el PDF.');
    } finally {
      setIsUploading(false);
    }
  }

  async function handleInvoiceSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setInvoiceError('');
    setInvoiceResult(null);

    if (!invoiceFile) {
      setInvoiceError('Selecciona una factura PDF antes de extraer datos.');
      return;
    }

    const formData = new FormData();
    formData.append('file', invoiceFile);
    setIsExtractingInvoice(true);

    try {
      const response = await fetch(`${API_BASE_URL}/extract-invoice`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const payload = (await response.json()) as InvoiceExtractionResponse;
      setInvoiceResult(payload);
    } catch (error) {
      setInvoiceError(error instanceof Error ? error.message : 'No se pudo extraer la factura.');
    } finally {
      setIsExtractingInvoice(false);
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
          { id: optimisticId, question: normalizedQuestion, answer: '', model: 'streaming', usedLlm: true, sources: [], agentSteps: [], createdAt },
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
              setChatMessages((messages) => messages.map((message) => message.id === optimisticId ? { ...message, answer: message.answer + data.token } : message));
            }
            if ('session_id' in data) {
              localStorage.setItem(SESSION_STORAGE_KEY, data.session_id);
              setSessionId(data.session_id);
              setChatMessages((messages) => messages.map((message) => message.id === optimisticId ? { ...message, model: data.model, sources: data.sources ?? [] } : message));
            }
          }
        }
      } else {
        const payload = (await response.json()) as ChatResponse;
        localStorage.setItem(SESSION_STORAGE_KEY, payload.session_id);
        setSessionId(payload.session_id);
        setChatMessages(payload.history.map(mapHistoryMessage));
      }
      setQuestion('');
      refreshSessions();
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'No se pudo responder la pregunta.');
    } finally {
      setIsAsking(false);
    }
  }

  function handleNewSession() {
    const nextSessionId = createSessionId();
    localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    setSessionId(nextSessionId);
    setChatMessages([]);
    setQuestion('');
    setChatError('');
  }

  function handleSelectSession(nextSessionId: string) {
    localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    setSessionId(nextSessionId);
    setChatError('');
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Nivel 11 - IA multimodal + RAG</p>
          <h1>AI Research Assistant</h1>
          <p className="hero-copy">
            Sube PDFs, aplica OCR cuando haga falta, extrae facturas a JSON y conversa con un agente RAG con fuentes.
          </p>
        </div>
        <div className="api-pill">Sesion: {sessionId.slice(0, 8)}</div>
      </section>

      <section className="grid-layout">
        <div className="side-stack">
          <article className="card upload-card">
            <div className="card-heading">
              <span className="step-number">1</span>
              <div>
                <h2>Subir PDF</h2>
                <p>El backend extrae texto, divide el documento e indexa los chunks en ChromaDB.</p>
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
                {isUploading ? 'Subiendo e indexando...' : 'Subir e indexar PDF'}
              </button>
            </form>

            {uploadError && <p className="status error">{uploadError}</p>}
            {uploadResult && (
              <div className="status success">
                <strong>{uploadResult.message}</strong>
                <dl>
                  <div>
                    <dt>Archivo</dt>
                    <dd>{uploadResult.filename}</dd>
                  </div>
                  <div>
                    <dt>Paginas</dt>
                    <dd>{uploadResult.page_count}</dd>
                  </div>
                  <div>
                    <dt>Chunks</dt>
                    <dd>{uploadResult.chunks_indexed}</dd>
                  </div>
                  <div>
                    <dt>Texto</dt>
                    <dd>{uploadResult.character_count.toLocaleString()} caracteres</dd>
                  </div>
                  <div>
                    <dt>Método</dt>
                    <dd>{uploadResult.extraction_method.toUpperCase()}</dd>
                  </div>
                  <div>
                    <dt>OCR</dt>
                    <dd>{uploadResult.ocr_attempted ? 'Intentado' : 'No requerido'}</dd>
                  </div>
                </dl>
                <p className="preview">{uploadResult.text_preview}</p>
              </div>
            )}
          </article>

          <article className="card invoice-card">
            <div className="card-heading">
              <span className="step-number">2</span>
              <div>
                <h2>Factura PDF a JSON</h2>
                <p>Extrae cliente, importe, fecha y numero de factura con fallback OCR para PDFs escaneados.</p>
              </div>
            </div>

            <form className="upload-form" onSubmit={handleInvoiceSubmit}>
              <label className="file-dropzone compact">
                <input
                  accept="application/pdf"
                  type="file"
                  onChange={(event) => setInvoiceFile(event.target.files?.[0] ?? null)}
                />
                <span>{invoiceFile ? invoiceFile.name : 'Selecciona una factura PDF'}</span>
                {invoiceFile && <small>{formatBytes(invoiceFile.size)}</small>}
              </label>
              <button type="submit" disabled={isExtractingInvoice}>
                {isExtractingInvoice ? 'Extrayendo...' : 'Extraer JSON'}
              </button>
            </form>

            {invoiceError && <p className="status error">{invoiceError}</p>}
            {invoiceResult && (
              <div className="status success">
                <strong>Datos extraidos de {invoiceResult.filename}</strong>
                <dl>
                  <div>
                    <dt>Cliente</dt>
                    <dd>{invoiceResult.cliente || 'No detectado'}</dd>
                  </div>
                  <div>
                    <dt>Importe</dt>
                    <dd>
                      {invoiceResult.moneda ? `${invoiceResult.moneda} ` : ''}
                      {invoiceResult.importe}
                    </dd>
                  </div>
                  <div>
                    <dt>Fecha</dt>
                    <dd>{invoiceResult.fecha ?? 'No detectada'}</dd>
                  </div>
                  <div>
                    <dt>Factura</dt>
                    <dd>{invoiceResult.numero_factura ?? 'No detectada'}</dd>
                  </div>
                  <div>
                    <dt>Confianza</dt>
                    <dd>{Math.round(invoiceResult.confidence * 100)}%</dd>
                  </div>
                  <div>
                    <dt>Método</dt>
                    <dd>{invoiceResult.extraction_method.toUpperCase()}</dd>
                  </div>
                </dl>
                {invoiceResult.missing_fields.length > 0 && (
                  <p className="missing-fields">
                    Faltan: {invoiceResult.missing_fields.join(', ')}
                  </p>
                )}
                <pre className="json-preview">
                  {JSON.stringify(
                    {
                      cliente: invoiceResult.cliente,
                      importe: invoiceResult.importe,
                      moneda: invoiceResult.moneda,
                      fecha: invoiceResult.fecha,
                      numero_factura: invoiceResult.numero_factura,
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            )}
          </article>

          <article className="card history-card">
            <div className="card-heading">
              <span className="step-number">3</span>
              <div>
                <h2>Historial</h2>
                <p>{chatMessages.length} mensajes en la sesion actual.</p>
              </div>
            </div>

            <button className="secondary-button" type="button" onClick={handleNewSession}>
              Nueva conversacion
            </button>

            <div className="session-list">
              {sessions.length === 0 ? (
                <p className="muted">Todavia no hay conversaciones guardadas.</p>
              ) : (
                sessions.map((session) => (
                  <button
                    className={`session-button ${
                      session.session_id === sessionId ? 'active' : ''
                    }`}
                    key={session.session_id}
                    type="button"
                    onClick={() => handleSelectSession(session.session_id)}
                  >
                    <strong>{session.last_question || 'Conversacion sin titulo'}</strong>
                    <span>
                      {session.message_count} mensajes - {formatDate(session.updated_at)}
                    </span>
                  </button>
                ))
              )}
            </div>
          </article>
        </div>

        <article className="card chat-card">
          <div className="card-heading">
            <span className="step-number">4</span>
            <div>
              <h2>Preguntar al asistente</h2>
              <p>El modo agente usa un flujo tipo LangGraph: pensar, buscar, usar herramientas y decidir.</p>
            </div>
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
              RAG clasico
            </button>
            <button
              className={chatMode === 'stream' ? 'active' : ''}
              type="button"
              onClick={() => setChatMode('stream')}
            >
              Streaming SSE
            </button>
          </div>

          <form className="question-form" onSubmit={handleQuestionSubmit}>
            <textarea
              placeholder="Ejemplo: Cual es la idea principal del paper?"
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
            {isLoadingHistory ? (
              <div className="empty-state">
                <strong>Cargando historial.</strong>
                <span>Recuperando la conversacion guardada.</span>
              </div>
            ) : chatMessages.length === 0 ? (
              <div className="empty-state">
                <strong>Aun no hay preguntas.</strong>
                <span>Sube un PDF y empieza una conversacion con memoria.</span>
              </div>
            ) : (
              chatMessages.map((message) => (
                <section className="message" key={message.id}>
                  <p className="question">{message.question}</p>
                  <p className="answer">{message.answer}</p>
                  <div className="message-meta">
                    <span>Modelo: {message.model}</span>
                    <span>{message.usedLlm ? 'LLM activo' : 'Fallback local'}</span>
                    <span>{formatDate(message.createdAt)}</span>
                  </div>
                  {message.agentSteps.length > 0 && (
                    <details className="agent-steps" open>
                      <summary>Pasos del agente</summary>
                      <ol>
                        {message.agentSteps.map((step, index) => (
                          <li key={`${message.id}-step-${index}`}>
                            <strong>{step.name}</strong>
                            <span>{step.description}</span>
                            {(step.tool || step.decision) && (
                              <small>
                                {step.tool ? `Herramienta: ${step.tool}` : ''}
                                {step.tool && step.decision ? ' - ' : ''}
                                {step.decision ? `Decision: ${step.decision}` : ''}
                              </small>
                            )}
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                  {message.sources.length > 0 && (
                    <details>
                      <summary>Fuentes recuperadas ({message.sources.length})</summary>
                      <ul className="sources-list">
                        {message.sources.map((source, index) => (
                          <li key={`${source.document_id}-${source.page_number}-${index}`}>
                            <strong>
                              {source.filename} - pagina {source.page_number}
                            </strong>
                            <span className="source-distance">
                              Distancia: {formatDistance(source.distance)}
                            </span>
                            <p>{source.text}</p>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </section>
              ))
            )}
          </div>
        </article>
      </section>
    </main>
  );
}

export default App;