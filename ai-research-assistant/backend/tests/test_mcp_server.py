from app.rag import SearchResult
import app.mcp_server as mcp_server


def test_search_pdf_knowledge_base_tool_serializes_sources(monkeypatch):
    fake_results = [
        SearchResult(
            text="MCP exposes tools to AI clients.",
            filename="mcp.pdf",
            page_number=5,
            document_id="doc-mcp",
            distance=0.15,
        )
    ]
    monkeypatch.setattr(mcp_server, "search_similar_chunks", lambda **kwargs: fake_results)

    payload = mcp_server.search_pdf_knowledge_base.fn("What is MCP?", limit=50)

    assert payload == [
        {
            "text": "MCP exposes tools to AI clients.",
            "filename": "mcp.pdf",
            "page_number": 5,
            "document_id": "doc-mcp",
            "distance": 0.15,
        }
    ]


def test_ask_research_assistant_tool_returns_rag_payload(monkeypatch):
    fake_results = [
        SearchResult(
            text="RAG context",
            filename="rag.pdf",
            page_number=2,
            document_id="doc-rag",
            distance=0.2,
        )
    ]

    class FakeAnswer:
        answer = "Respuesta desde MCP."
        model = "test-model"
        used_llm = False
        estimated_prompt_tokens = 12
        included_contexts = 1

    monkeypatch.setattr(mcp_server, "search_similar_chunks", lambda **kwargs: fake_results)
    monkeypatch.setattr(mcp_server, "generate_rag_answer", lambda **kwargs: FakeAnswer())

    payload = mcp_server.ask_research_assistant.fn("Que dice el PDF?", limit=1)

    assert payload["answer"] == "Respuesta desde MCP."
    assert payload["model"] == "test-model"
    assert payload["sources"][0]["filename"] == "rag.pdf"
