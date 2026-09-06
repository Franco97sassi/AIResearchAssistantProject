from pathlib import Path

import fitz

from app import observability
from app.evaluation import evaluate_rag_response
from app.invoice import extract_invoice_fields
from app.pdf_loader import extract_text_from_pdf
from app.rag import SearchResult


def test_extract_invoice_fields_returns_values_and_confidence():
    invoice = extract_invoice_fields(
        "Cliente: Ada Lovelace\nFactura: INV-42\nFecha: 2026-09-06\nTotal: EUR 1.234,50"
    )

    assert invoice.cliente == "Ada Lovelace"
    assert invoice.numero_factura == "INV-42"
    assert invoice.fecha == "2026-09-06"
    assert invoice.importe == 1234.50
    assert invoice.moneda == "EUR"
    assert invoice.confidence == 1.0
    assert invoice.missing_fields == []


def test_extract_invoice_fields_reports_missing_values():
    invoice = extract_invoice_fields("Documento sin campos de factura")

    assert invoice.confidence == 0.0
    assert set(invoice.missing_fields) == {"cliente", "importe", "fecha", "numero_factura"}


def test_pdf_loader_extracts_text_and_page_number(tmp_path: Path):
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "RAG demo document")
    document.save(pdf_path)
    document.close()

    result = extract_text_from_pdf(pdf_path)

    assert result.page_count == 1
    assert result.pages[0].page_number == 1
    assert "RAG demo document" in result.text
    assert result.extraction_method == "text"


def test_evaluation_marks_cited_supported_answer_as_grounded():
    source = SearchResult(
        text="RAG combina recuperacion semantica con generacion.",
        filename="rag.pdf",
        page_number=2,
        document_id="doc-rag",
        distance=0.1,
    )

    result = evaluate_rag_response(
        question="Que combina RAG?",
        answer="RAG combina recuperacion semantica con generacion (fuente rag.pdf, pagina 2).",
        sources=[source],
    )

    assert result.grounded is True
    assert result.hallucination_risk == "low"
    assert result.prompt_injection_detected is False


def test_observability_persists_and_aggregates_events(tmp_path, monkeypatch):
    database = tmp_path / "metrics.sqlite3"
    monkeypatch.setattr(observability, "LOG_DIR", tmp_path)
    monkeypatch.setattr(observability, "METRICS_DB_PATH", database)

    observability.log_event(
        "chat",
        latency_ms=25,
        model="local-test",
        source_count=2,
        estimated_tokens=40,
        request_id="demo",
    )
    metrics = observability.collect_metrics()

    assert metrics["event_count"] == 1
    assert metrics["average_latency_ms"] == 25.0
    assert metrics["total_estimated_tokens"] == 40
    assert metrics["events_by_type"] == [{"event_type": "chat", "count": 1}]
    assert metrics["recent_events"][0]["metadata"] == {"request_id": "demo"}
