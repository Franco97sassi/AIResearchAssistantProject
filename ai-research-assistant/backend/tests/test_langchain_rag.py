from pathlib import Path

from app.langchain_rag import (
    build_langchain_documents,
    build_langchain_rag_prompt,
    build_langchain_retriever,
    get_langchain_component_status,
    load_pdf_with_langchain,
    page_from_langchain_document,
)
from app.pdf_loader import PDFPage, PDFTextExtractionResult


def test_langchain_document_contract_has_page_content_and_metadata():
    extraction = PDFTextExtractionResult(pages=[PDFPage(page_number=2, text="Contenido del paper")])

    documents = build_langchain_documents(
        extraction,
        filename="paper.pdf",
        stored_filename="stored.pdf",
        document_id="doc-1",
    )

    first_document = documents[0]
    if isinstance(first_document, dict):
        assert first_document["page_content"] == "Contenido del paper"
        metadata = first_document["metadata"]
    else:
        assert first_document.page_content == "Contenido del paper"
        metadata = first_document.metadata
    assert metadata["filename"] == "paper.pdf"
    assert metadata["stored_filename"] == "stored.pdf"
    assert metadata["document_id"] == "doc-1"
    assert metadata["page_number"] == 2


def test_langchain_prompt_fallback_keeps_rag_sections():
    prompt = build_langchain_rag_prompt(
        system_prompt="Sistema",
        question="Que dice el PDF?",
        history_block="Sin historial previo.",
        context_block="Fuente 1",
    )

    if isinstance(prompt, dict):
        assert prompt["system"] == "Sistema"
        assert "Que dice el PDF?" in prompt["user"]
        assert "Fuente 1" in prompt["user"]
    else:
        messages = prompt.format_messages(
            question="Que dice el PDF?",
            history_block="Sin historial previo.",
            context_block="Fuente 1",
        )
        assert messages[0].content == "Sistema"
        assert "Fuente 1" in messages[1].content


def test_langchain_status_and_loader_are_safe_without_optional_packages():
    status = get_langchain_component_status()

    assert isinstance(status.enabled, bool)
    if not status.pdf_loader:
        assert load_pdf_with_langchain(Path("missing.pdf")) == []


def test_page_from_langchain_document_normalizes_document_like_mapping():
    page = page_from_langchain_document(
        {
            "page_content": "Texto normalizado",
            "metadata": {"page": 3, "extraction_method": "langchain"},
        },
        fallback_page_number=1,
    )

    assert page.page_number == 3
    assert page.text == "Texto normalizado"
    assert page.extraction_method == "langchain"


def test_langchain_retriever_adapter_returns_document_contract():
    class Result:
        text = "Fragmento recuperado"
        filename = "paper.pdf"
        page_number = 4
        document_id = "doc-2"
        distance = 0.12

    calls = {}

    def fake_search_tool(query: str, limit: int):
        calls["query"] = query
        calls["limit"] = limit
        return [Result()]

    retriever = build_langchain_retriever(fake_search_tool, limit=3)
    documents = retriever.invoke({"query": "agentes"})

    assert calls == {"query": "agentes", "limit": 3}
    first_document = documents[0]
    if isinstance(first_document, dict):
        assert first_document["page_content"] == "Fragmento recuperado"
        metadata = first_document["metadata"]
    else:
        assert first_document.page_content == "Fragmento recuperado"
        metadata = first_document.metadata
    assert metadata["filename"] == "paper.pdf"
    assert metadata["page_number"] == 4
