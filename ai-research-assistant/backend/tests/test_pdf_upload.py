from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.main import app
from app.pdf_loader import extract_text_from_pdf
from app.rag import SearchResult

client = TestClient(app)


def create_pdf(path: Path, text: str = "Machine learning research notes") -> Path:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    return path


def test_extract_text_from_pdf_reads_page_text(tmp_path):
    pdf_path = create_pdf(tmp_path / "paper.pdf", "Retrieval augmented generation")

    result = extract_text_from_pdf(pdf_path)

    assert result.page_count == 1
    assert "Retrieval augmented generation" in result.text
    assert result.character_count > 0


def test_upload_pdf_returns_extraction_metadata(tmp_path, monkeypatch):
    pdf_path = create_pdf(tmp_path / "paper.pdf", "AI research assistant content")

    class FakeIndexingResult:
        document_id = "doc-test"
        chunks_indexed = 1
        collection_name = "research_papers"

    monkeypatch.setattr("app.main.index_pdf_text", lambda *args: FakeIndexingResult())

    with pdf_path.open("rb") as pdf_file:
        response = client.post(
            "/upload-pdf",
            files={"file": ("paper.pdf", pdf_file, "application/pdf")},
        )

    assert response.status_code == 201
    payload = response.json()
    assert "PDF subido" in payload["message"]
    assert payload["filename"] == "paper.pdf"
    assert payload["page_count"] == 1
    assert payload["character_count"] > 0
    assert "AI research assistant content" in payload["text_preview"]
    assert payload["document_id"] == "doc-test"
    assert payload["chunks_indexed"] == 1
    assert payload["collection_name"] == "research_papers"
    stored_path = UPLOAD_DIR / payload["stored_filename"]
    stored_path.unlink(missing_ok=True)


def test_chat_returns_answer_with_sources_and_history(monkeypatch):
    fake_results = [
        SearchResult(
            text="RAG combines retrieval with a language model.",
            filename="rag-paper.pdf",
            page_number=2,
            document_id="doc-rag",
            distance=0.12,
        )
    ]

    class FakeRAGAnswer:
        answer = "RAG combina recuperacion con generacion."
        model = "test-model"
        used_llm = True

    def fake_append_chat_exchange(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "messages": [
                {
                    "id": "message-test",
                    "question": kwargs["question"],
                    "answer": kwargs["answer"],
                    "model": kwargs["model"],
                    "used_llm": kwargs["used_llm"],
                    "sources": kwargs["sources"],
                    "created_at": "2026-06-07T00:00:00Z",
                }
            ],
        }

    monkeypatch.setattr(
        "app.main.search_similar_chunks", lambda *args, **kwargs: fake_results
    )
    monkeypatch.setattr("app.main.generate_rag_answer", lambda *args: FakeRAGAnswer())
    monkeypatch.setattr("app.main.get_recent_history", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.main.append_chat_exchange", fake_append_chat_exchange)

    response = client.post(
        "/chat",
        json={
            "question": "Que es RAG?",
            "limit": 1,
            "session_id": "session-test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session-test"
    assert payload["question"] == "Que es RAG?"
    assert payload["answer"] == "RAG combina recuperacion con generacion."
    assert payload["model"] == "test-model"
    assert payload["used_llm"] is True
    assert payload["sources"][0]["filename"] == "rag-paper.pdf"
    assert payload["sources"][0]["page_number"] == 2
    assert payload["history"][0]["question"] == "Que es RAG?"


def test_chat_rejects_empty_question():
    response = client.post("/chat", json={"question": "", "limit": 1})

    assert response.status_code == 422


def test_cors_allows_local_react_frontend():
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

def test_agent_chat_returns_steps_and_history(monkeypatch):
    class FakeStep:
        name = "buscar"
        description = "Use busqueda semantica."
        tool = "search_similar_chunks"
        decision = "contexto_encontrado"

    class FakeAgentRun:
        answer = "Respuesta agentica."
        model = "test-agent"
        used_llm = False
        sources = [
            SearchResult(
                text="Agent context",
                filename="agent.pdf",
                page_number=4,
                document_id="doc-agent",
                distance=0.2,
            )
        ]
        steps = [FakeStep()]
        framework = "langgraph"
        estimated_prompt_tokens = 42
        included_contexts = 1

    def fake_append_chat_exchange(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "messages": [
                {
                    "id": "message-agent",
                    "question": kwargs["question"],
                    "answer": kwargs["answer"],
                    "model": kwargs["model"],
                    "used_llm": kwargs["used_llm"],
                    "sources": kwargs["sources"],
                    "agent_steps": kwargs["agent_steps"],
                    "created_at": "2026-06-10T00:00:00Z",
                }
            ],
        }

    monkeypatch.setattr("app.main.get_recent_history", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.main.run_research_agent", lambda **kwargs: FakeAgentRun())
    monkeypatch.setattr("app.main.append_chat_exchange", fake_append_chat_exchange)

    response = client.post(
        "/agent/chat",
        json={
            "question": "Como funciona el agente?",
            "limit": 1,
            "session_id": "session-agent",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Respuesta agentica."
    assert payload["agent_framework"] == "langgraph"
    assert payload["agent_steps"][0]["tool"] == "search_similar_chunks"
    assert payload["sources"][0]["filename"] == "agent.pdf"
    assert payload["history"][0]["agent_steps"][0]["decision"] == "contexto_encontrado"

def test_extract_invoice_returns_structured_fields(tmp_path):
    invoice_text = """
    Factura: FAC-2026-001
    Fecha: 2026-06-14
    Cliente: ACME Research LLC
    Total: USD 1250.75
    """
    pdf_path = create_pdf(tmp_path / "invoice.pdf", invoice_text)

    with pdf_path.open("rb") as pdf_file:
        response = client.post(
            "/extract-invoice",
            files={"file": ("invoice.pdf", pdf_file, "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "invoice.pdf"
    assert payload["cliente"] == "ACME Research LLC"
    assert payload["importe"] == 1250.75
    assert payload["moneda"] == "USD"
    assert payload["fecha"] == "2026-06-14"
    assert payload["numero_factura"] == "FAC-2026-001"
    assert payload["confidence"] == 1.0
    assert payload["missing_fields"] == []
    assert payload["extraction_method"] == "text"
    stored_path = UPLOAD_DIR / payload["stored_filename"]
    stored_path.unlink(missing_ok=True)

def test_cors_allows_localhost_dev_ports_for_agent_chat():
    response = client.options(
        "/agent/chat",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"

def test_upload_pdf_reports_extraction_method(tmp_path, monkeypatch):
    pdf_path = create_pdf(tmp_path / "paper.pdf", "Selectable PDF text")

    class FakeIndexingResult:
        document_id = "doc-method"
        chunks_indexed = 1
        collection_name = "research_papers"

    monkeypatch.setattr("app.main.index_pdf_text", lambda *args: FakeIndexingResult())

    with pdf_path.open("rb") as pdf_file:
        response = client.post(
            "/upload-pdf",
            files={"file": ("paper.pdf", pdf_file, "application/pdf")},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["extraction_method"] == "text"
    assert payload["ocr_attempted"] is False
    assert payload["ocr_available"] is True
    stored_path = UPLOAD_DIR / payload["stored_filename"]
    stored_path.unlink(missing_ok=True)