"""MCP server that exposes the research assistant as external AI tools.

Run it with:
    python -m app.mcp_server

The server uses stdio transport so clients such as Claude Desktop, Cursor or
other MCP-compatible hosts can call the same PDF search/RAG capabilities that
power the FastAPI app.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from app.agent import run_research_agent
from app.llm import generate_rag_answer
from app.rag import SearchResult, list_indexed_documents, search_similar_chunks

if (
    importlib.util.find_spec("mcp") is not None
    and importlib.util.find_spec("mcp.server.fastmcp") is not None
):
    from mcp.server.fastmcp import FastMCP
else:

    class _LocalTool:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args, **kwargs):
            return self.fn(*args, **kwargs)

    class FastMCP:
        """Tiny test fallback used only when the optional MCP package is absent."""

        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(fn):
                return _LocalTool(fn)

            return decorator

        def run(self, transport: str = "stdio") -> None:
            raise RuntimeError("Instala la dependencia 'mcp' para ejecutar el servidor MCP real.")


mcp = FastMCP("ai-research-assistant")


def _serialize_search_result(result: SearchResult) -> dict[str, Any]:
    return {
        "text": result.text,
        "filename": result.filename,
        "page_number": result.page_number,
        "document_id": result.document_id,
        "distance": result.distance,
    }


@mcp.tool()
def list_documents() -> list[dict[str, Any]]:
    """List PDF documents currently indexed in the assistant vector store."""
    return list_indexed_documents()


@mcp.tool()
def search_pdf_knowledge_base(question: str, limit: int = 4) -> list[dict[str, Any]]:
    """Search indexed PDF chunks semantically and return grounded sources."""
    safe_limit = max(1, min(limit, 10))
    results = search_similar_chunks(question=question, limit=safe_limit)
    return [_serialize_search_result(result) for result in results]


@mcp.tool()
def ask_research_assistant(question: str, limit: int = 4) -> dict[str, Any]:
    """Ask the RAG assistant a question over the indexed PDFs."""
    safe_limit = max(1, min(limit, 10))
    results = search_similar_chunks(question=question, limit=safe_limit)
    answer = generate_rag_answer(question=question, contexts=results, history=None)
    return {
        "question": question,
        "answer": answer.answer,
        "model": answer.model,
        "used_llm": answer.used_llm,
        "estimated_prompt_tokens": answer.estimated_prompt_tokens,
        "included_contexts": answer.included_contexts,
        "sources": [_serialize_search_result(result) for result in results],
    }


@mcp.tool()
def ask_research_agent(question: str, limit: int = 4) -> dict[str, Any]:
    """Ask the lightweight agentic RAG flow and return its visible steps."""
    safe_limit = max(1, min(limit, 10))
    agent_run = run_research_agent(question=question, limit=safe_limit)
    return {
        "question": question,
        "answer": agent_run.answer,
        "model": agent_run.model,
        "used_llm": agent_run.used_llm,
        "agent_framework": agent_run.framework,
        "estimated_prompt_tokens": agent_run.estimated_prompt_tokens,
        "included_contexts": agent_run.included_contexts,
        "sources": [_serialize_search_result(result) for result in agent_run.sources],
        "agent_steps": [
            {
                "name": step.name,
                "description": step.description,
                "tool": step.tool,
                "decision": step.decision,
            }
            for step in agent_run.steps
        ],
    }


def main() -> None:
    """Start the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
