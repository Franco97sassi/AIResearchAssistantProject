import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agent import AgentStep, run_research_agent
from app.chat_history import (
    append_chat_exchange,
    build_retrieval_query,
    filter_history_for_document,
    get_recent_history,
    get_session,
    list_sessions,
    normalize_session_id,
)
from app.config import (
    ALLOWED_ORIGIN_REGEX,
    ALLOWED_ORIGINS,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
    UPLOAD_DIR,
)
from app.evaluation import evaluate_rag_response
from app.guardrails import answer_has_required_sources, inspect_text
from app.invoice import extract_invoice_fields
from app.jobs import enqueue_pdf, fetch_job, job_belongs_to, serialize_job
from app.llm import generate_rag_answer
from app.observability import (
    collect_metrics,
    current_trace_id,
    get_trace,
    init_observability,
    log_event,
    prometheus_metrics,
)
from app.pdf_loader import extract_text_from_pdf
from app.rag import SearchResult, index_pdf_text, search_similar_chunks
from app.security import Principal, get_principal


class InvoiceExtractionResponse(BaseModel):
    filename: str
    stored_filename: str
    page_count: int
    character_count: int
    extraction_method: str
    ocr_attempted: bool
    ocr_available: bool
    cliente: str
    importe: float
    moneda: str | None
    fecha: str | None
    numero_factura: str | None
    confidence: float
    missing_fields: list[str]
    text_preview: str


class SearchResultPayload(BaseModel):
    text: str
    filename: str
    page_number: int
    document_id: str
    distance: float | None = None


class RAGEvaluationRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    sources: list[SearchResultPayload] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Pregunta sobre los PDFs")
    session_id: str | None = Field(
        default=None,
        description="Identificador de la conversación para historial y memoria",
    )
    limit: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Cantidad máxima de fragmentos relevantes a recuperar",
    )
    document_id: str | None = Field(
        default=None,
        description="Opcional: limita la recuperación a un PDF indexado concreto",
    )


def validate_question(question: str) -> dict[str, object]:
    """Reject prompt-injection attempts before any retrieval or model call."""
    guardrail = inspect_text(question)
    if not guardrail.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "La pregunta parece contener prompt injection.",
                "guardrails": guardrail.__dict__,
            },
        )
    return guardrail.__dict__


def serialize_search_result(result: SearchResult) -> dict[str, object]:
    return {
        "text": result.text,
        "filename": result.filename,
        "page_number": result.page_number,
        "document_id": result.document_id,
        "distance": result.distance,
    }


def serialize_agent_step(step: AgentStep) -> dict[str, object]:
    return {
        "name": step.name,
        "description": step.description,
        "tool": step.tool,
        "decision": step.decision,
        "role": getattr(step, "role", None),
    }


def _scoped_session_id(session_id: str | None, principal: Principal) -> str:
    normalized = normalize_session_id(session_id)
    return f"{principal.tenant_id}:{normalized}" if principal.authenticated else normalized


@asynccontextmanager
async def lifespan(_app: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_observability()
    yield


app = FastAPI(
    title="AI Research Assistant",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    trace_id = request.headers.get("X-Request-ID") or uuid4().hex
    token = current_trace_id.set(trace_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
    finally:
        log_event(
            "http_request",
            latency_ms=(time.perf_counter() - started_at) * 1000,
            method=request.method,
            path=request.url.path,
        )
        current_trace_id.reset(token)


@app.get("/")
def root():
    return {"message": "AI Research Assistant API funcionando"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-research-assistant"}


@app.get("/metrics")
def metrics(_principal: Principal = Depends(get_principal)):
    return collect_metrics()


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def metrics_prometheus(_principal: Principal = Depends(get_principal)):
    return prometheus_metrics()


@app.get("/traces/{trace_id}")
def trace(trace_id: str, _principal: Principal = Depends(get_principal)):
    return {"trace_id": trace_id, "events": get_trace(trace_id)}


@app.get("/ai-topics")
def ai_topics():
    return {
        "free_first": True,
        "covered": [
            "RAG",
            "Chunking",
            "Embeddings",
            "Metadata",
            "Vector Search",
            "Semantic Search",
            "Hybrid Search",
            "Reranking",
            "Grounding",
            "Citations",
            "MCP Server Tools",
            "LangChain adapters",
            "LangGraph-style agents",
            "Agent reflection/context critique",
            "PII detection",
            "Prompt injection guardrails",
            "Token/context optimization",
            "Streaming SSE",
            "Local AI metrics",
            "Deterministic RAG evaluation",
            "Document understanding with OCR",
        ],
        "intentionally_excluded_paid_model_apis": [
            "OpenAI",
            "Anthropic",
            "Gemini",
            "Mistral",
            "DeepSeek",
            "OpenRouter",
        ],
        "next_steps": [
            "Add FAISS or Qdrant as an optional local vector store",
            "Add prompt version files for prompt management",
            "Add a local feedback endpoint for human-in-the-loop review",
            "Add multimodal image understanding only if a local VLM is available",
        ],
    }


@app.post("/evaluation/rag")
def evaluate_rag(request: RAGEvaluationRequest, _principal: Principal = Depends(get_principal)):
    sources = [
        SearchResult(
            text=source.text,
            filename=source.filename,
            page_number=source.page_number,
            document_id=source.document_id,
            distance=source.distance,
        )
        for source in request.sources
    ]
    evaluation = evaluate_rag_response(
        question=request.question,
        answer=request.answer,
        sources=sources,
    )
    return evaluation.__dict__


async def _save_pdf_upload(file: UploadFile) -> tuple[str, str, Path, int]:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes enviar un archivo PDF.",
        )

    original_filename = Path(file.filename).name
    if not original_filename.lower().endswith(".pdf") or file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten archivos PDF.",
        )

    safe_filename = f"{uuid4().hex}_{original_filename}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / safe_filename
    bytes_written = 0

    try:
        with destination.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                    buffer.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"El PDF no puede superar {MAX_UPLOAD_SIZE_MB} MB.",
                    )
                await run_in_threadpool(buffer.write, chunk)
    finally:
        await file.close()

    return original_filename, safe_filename, destination, bytes_written


def _empty_pdf_error(extraction_result) -> HTTPException:
    if extraction_result.ocr_attempted and not extraction_result.ocr_available:
        detail = (
            "No se pudo extraer texto del PDF y el OCR local no esta disponible. "
            "Instala Tesseract/idiomas OCR o usa un PDF con texto seleccionable."
        )
    else:
        detail = (
            "No se pudo extraer texto del PDF. "
            "Prueba con un PDF que contenga texto seleccionable o escaneos legibles."
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


@app.post("/upload-pdf", status_code=status.HTTP_201_CREATED)
async def upload_pdf(file: UploadFile = File(...), principal: Principal = Depends(get_principal)):
    original_filename, safe_filename, destination, bytes_written = await _save_pdf_upload(file)
    extraction_result = await run_in_threadpool(
        extract_text_from_pdf, destination, use_ocr_fallback=True
    )

    if extraction_result.character_count == 0:
        destination.unlink(missing_ok=True)
        raise _empty_pdf_error(extraction_result)

    indexing_result = await run_in_threadpool(
        index_pdf_text,
        extraction_result,
        original_filename,
        safe_filename,
        owner_id=principal.tenant_id,
    )

    return {
        "message": "PDF subido, texto extraído e indexado correctamente",
        "filename": original_filename,
        "stored_filename": safe_filename,
        "size_bytes": bytes_written,
        "page_count": extraction_result.page_count,
        "character_count": extraction_result.character_count,
        "extraction_method": extraction_result.extraction_method,
        "ocr_attempted": extraction_result.ocr_attempted,
        "ocr_available": extraction_result.ocr_available,
        "text_preview": extraction_result.text[:500],
        "document_id": indexing_result.document_id,
        "chunks_indexed": indexing_result.chunks_indexed,
        "collection_name": indexing_result.collection_name,
    }


@app.post("/jobs/upload-pdf", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_pdf_upload(
    file: UploadFile = File(...), principal: Principal = Depends(get_principal)
):
    """Persist an upload quickly and delegate OCR/indexing to an RQ worker."""
    original_filename, safe_filename, destination, bytes_written = await _save_pdf_upload(file)
    try:
        job = await run_in_threadpool(
            enqueue_pdf, destination, original_filename, safe_filename, principal.tenant_id
        )
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=503, detail="La cola de procesamiento no esta disponible"
        ) from exc
    return {"job_id": job.id, "status": "queued", "size_bytes": bytes_written}


@app.get("/jobs/{job_id}")
async def get_pdf_job(job_id: str, principal: Principal = Depends(get_principal)):
    try:
        job = await run_in_threadpool(fetch_job, job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado") from exc
    if not job_belongs_to(job, principal.tenant_id):
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return serialize_job(job)


@app.post("/extract-invoice", response_model=InvoiceExtractionResponse)
async def extract_invoice(
    file: UploadFile = File(...), _principal: Principal = Depends(get_principal)
):
    original_filename, safe_filename, destination, _bytes_written = await _save_pdf_upload(file)
    extraction_result = await run_in_threadpool(
        extract_text_from_pdf, destination, use_ocr_fallback=True
    )

    if extraction_result.character_count == 0:
        destination.unlink(missing_ok=True)
        raise _empty_pdf_error(extraction_result)

    invoice = await run_in_threadpool(extract_invoice_fields, extraction_result.text)

    return InvoiceExtractionResponse(
        filename=original_filename,
        stored_filename=safe_filename,
        page_count=extraction_result.page_count,
        character_count=extraction_result.character_count,
        extraction_method=extraction_result.extraction_method,
        ocr_attempted=extraction_result.ocr_attempted,
        ocr_available=extraction_result.ocr_available,
        cliente=invoice.cliente,
        importe=invoice.importe,
        moneda=invoice.moneda,
        fecha=invoice.fecha,
        numero_factura=invoice.numero_factura,
        confidence=invoice.confidence,
        missing_fields=invoice.missing_fields,
        text_preview=extraction_result.text[:500],
    )


@app.get("/search")
def search_pdf_chunks(
    question: str = Query(..., min_length=1),
    limit: int = Query(default=4, ge=1, le=10),
    document_id: str | None = Query(default=None),
    principal: Principal = Depends(get_principal),
):
    results = search_similar_chunks(
        question=question, limit=limit, document_id=document_id, owner_id=principal.tenant_id
    )
    return {
        "question": question,
        "results": [serialize_search_result(result) for result in results],
    }


@app.get("/chat/sessions")
def list_chat_sessions(principal: Principal = Depends(get_principal)):
    sessions = list_sessions()
    if principal.authenticated:
        prefix = f"{principal.tenant_id}:"
        sessions = [item for item in sessions if str(item["session_id"]).startswith(prefix)]
        for item in sessions:
            item["session_id"] = str(item["session_id"])[len(prefix) :]
    return {"sessions": sessions}


@app.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str, principal: Principal = Depends(get_principal)):
    session = get_session(_scoped_session_id(session_id, principal))
    session["session_id"] = session_id
    return session


@app.post("/chat")
async def chat_with_pdfs(request: ChatRequest, principal: Principal = Depends(get_principal)):
    started_at = time.perf_counter()
    guardrail = validate_question(request.question)
    public_session_id = normalize_session_id(request.session_id)
    session_id = _scoped_session_id(public_session_id, principal)
    history = await run_in_threadpool(get_recent_history, session_id)
    scoped_history = filter_history_for_document(history, request.document_id)
    retrieval_query = build_retrieval_query(request.question, scoped_history)
    results = await run_in_threadpool(
        search_similar_chunks,
        question=retrieval_query,
        limit=request.limit,
        document_id=request.document_id,
        owner_id=principal.tenant_id,
    )
    rag_answer = await run_in_threadpool(
        generate_rag_answer, request.question, results, scoped_history
    )
    sources = [serialize_search_result(result) for result in results]
    answer_text = rag_answer.answer
    sources_validated = answer_has_required_sources(answer_text, len(sources))
    session = await run_in_threadpool(
        append_chat_exchange,
        session_id=session_id,
        question=request.question,
        answer=answer_text,
        model=rag_answer.model,
        used_llm=rag_answer.used_llm,
        sources=sources,
    )

    log_event(
        "chat",
        latency_ms=(time.perf_counter() - started_at) * 1000,
        model=rag_answer.model,
        source_count=len(sources),
        estimated_tokens=getattr(rag_answer, "estimated_prompt_tokens", 0),
        estimated_output_tokens=max(1, len(answer_text) // 4),
        guardrails=guardrail,
        sources_validated=sources_validated,
    )

    return {
        "session_id": public_session_id,
        "question": request.question,
        "answer": answer_text,
        "model": rag_answer.model,
        "used_llm": rag_answer.used_llm,
        "estimated_prompt_tokens": getattr(rag_answer, "estimated_prompt_tokens", None),
        "included_contexts": getattr(rag_answer, "included_contexts", len(sources)),
        "sources": sources,
        "history": session["messages"],
    }


@app.post("/chat/stream")
async def stream_chat_with_pdfs(
    request: ChatRequest, principal: Principal = Depends(get_principal)
):
    started_at = time.perf_counter()
    guardrail = validate_question(request.question)
    public_session_id = normalize_session_id(request.session_id)
    session_id = _scoped_session_id(public_session_id, principal)
    history = await run_in_threadpool(get_recent_history, session_id)
    scoped_history = filter_history_for_document(history, request.document_id)
    retrieval_query = build_retrieval_query(request.question, scoped_history)
    results = await run_in_threadpool(
        search_similar_chunks,
        question=retrieval_query,
        limit=request.limit,
        document_id=request.document_id,
        owner_id=principal.tenant_id,
    )
    rag_answer = await run_in_threadpool(
        generate_rag_answer, request.question, results, scoped_history
    )
    sources = [serialize_search_result(result) for result in results]
    await run_in_threadpool(
        append_chat_exchange,
        session_id=session_id,
        question=request.question,
        answer=rag_answer.answer,
        model=rag_answer.model,
        used_llm=rag_answer.used_llm,
        sources=sources,
    )
    log_event(
        "chat_stream",
        latency_ms=(time.perf_counter() - started_at) * 1000,
        model=rag_answer.model,
        source_count=len(sources),
        estimated_tokens=getattr(rag_answer, "estimated_prompt_tokens", 0),
        estimated_output_tokens=max(1, len(rag_answer.answer) // 4),
        guardrails=guardrail,
    )

    async def event_stream():
        yield f"event: metadata\ndata: {json.dumps({'session_id': public_session_id, 'model': rag_answer.model, 'sources': sources}, ensure_ascii=False)}\n\n"
        for chunk in rag_answer.answer.split():
            yield f"event: token\ndata: {json.dumps({'token': chunk + ' '}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/agent/chat")
async def chat_with_research_agent(
    request: ChatRequest, principal: Principal = Depends(get_principal)
):
    validate_question(request.question)
    public_session_id = normalize_session_id(request.session_id)
    session_id = _scoped_session_id(public_session_id, principal)
    history = await run_in_threadpool(get_recent_history, session_id)
    scoped_history = filter_history_for_document(history, request.document_id)
    agent_run = await run_in_threadpool(
        run_research_agent,
        question=request.question,
        history=scoped_history,
        limit=request.limit,
        document_id=request.document_id,
        owner_id=principal.tenant_id,
    )
    sources = [serialize_search_result(result) for result in agent_run.sources]
    agent_steps = [serialize_agent_step(step) for step in agent_run.steps]
    session = await run_in_threadpool(
        append_chat_exchange,
        session_id=session_id,
        question=request.question,
        answer=agent_run.answer,
        model=agent_run.model,
        used_llm=agent_run.used_llm,
        sources=sources,
        agent_steps=agent_steps,
    )

    return {
        "session_id": public_session_id,
        "question": request.question,
        "answer": agent_run.answer,
        "model": agent_run.model,
        "used_llm": agent_run.used_llm,
        "sources": sources,
        "agent_steps": agent_steps,
        "agent_framework": agent_run.framework,
        "estimated_prompt_tokens": agent_run.estimated_prompt_tokens,
        "included_contexts": agent_run.included_contexts,
        "history": session["messages"],
    }


app = CORSMiddleware(
    app=app,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
