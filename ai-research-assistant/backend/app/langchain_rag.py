from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module, util
from pathlib import Path
from typing import Any

from app.pdf_loader import PDFPage, PDFTextExtractionResult


@dataclass(frozen=True)
class LangChainComponentStatus:
    """Availability report for optional LangChain RAG components."""

    document: bool
    text_splitter: bool
    pdf_loader: bool
    prompt_template: bool

    @property
    def enabled(self) -> bool:
        return self.document and self.text_splitter


def _has_module(module_name: str) -> bool:
    module_parts = module_name.split(".")
    for part_index in range(1, len(module_parts) + 1):
        candidate = ".".join(module_parts[:part_index])
        if util.find_spec(candidate) is None:
            return False
    return True


def get_langchain_component_status() -> LangChainComponentStatus:
    """Return which optional LangChain building blocks are importable."""
    return LangChainComponentStatus(
        document=_has_module("langchain_core.documents"),
        text_splitter=_has_module("langchain_text_splitters"),
        pdf_loader=_has_module("langchain_community.document_loaders"),
        prompt_template=_has_module("langchain_core.prompts"),
    )


def _document_class() -> type[Any] | None:
    if not _has_module("langchain_core.documents"):
        return None
    return import_module("langchain_core.documents").Document


def _recursive_splitter_class() -> type[Any] | None:
    if not _has_module("langchain_text_splitters"):
        return None
    return import_module("langchain_text_splitters").RecursiveCharacterTextSplitter


def _chat_prompt_template_class() -> type[Any] | None:
    if not _has_module("langchain_core.prompts"):
        return None
    return import_module("langchain_core.prompts").ChatPromptTemplate


def build_langchain_documents(
    extraction_result: PDFTextExtractionResult,
    *,
    filename: str,
    stored_filename: str = "",
    document_id: str = "",
) -> list[Any]:
    """Convert extracted PDF pages into LangChain `Document` objects when available.

    The fallback shape mirrors LangChain's `page_content` and `metadata` fields
    so tests and local/offline runs can use the same data contract even before
    installing the optional LangChain packages.
    """
    document_class = _document_class()
    documents: list[Any] = []
    for page in extraction_result.pages:
        metadata = {
            "source": filename,
            "filename": filename,
            "stored_filename": stored_filename,
            "document_id": document_id,
            "page": page.page_number,
            "page_number": page.page_number,
            "extraction_method": page.extraction_method,
        }
        if document_class is None:
            documents.append({"page_content": page.text, "metadata": metadata})
            continue
        documents.append(document_class(page_content=page.text, metadata=metadata))
    return documents


def load_pdf_with_langchain(pdf_path: Path) -> list[Any]:
    """Load a PDF through LangChain's PyPDFLoader when the package is installed."""
    if not _has_module("langchain_community.document_loaders"):
        return []
    loader_class = import_module("langchain_community.document_loaders").PyPDFLoader
    return loader_class(str(pdf_path)).load()


def split_text_with_langchain(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str] | None:
    """Split text using LangChain's RecursiveCharacterTextSplitter if available."""
    splitter_class = _recursive_splitter_class()
    if splitter_class is None:
        return None
    splitter = splitter_class(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def search_results_to_langchain_documents(search_results: list[Any]) -> list[Any]:
    """Convert retrieved SearchResult-like objects into LangChain documents."""
    document_class = _document_class()
    documents: list[Any] = []
    for result in search_results:
        metadata = {
            "source": getattr(result, "filename", ""),
            "filename": getattr(result, "filename", ""),
            "page": getattr(result, "page_number", 0),
            "page_number": getattr(result, "page_number", 0),
            "document_id": getattr(result, "document_id", ""),
            "distance": getattr(result, "distance", None),
        }
        page_content = str(getattr(result, "text", ""))
        if document_class is None:
            documents.append({"page_content": page_content, "metadata": metadata})
            continue
        documents.append(document_class(page_content=page_content, metadata=metadata))
    return documents


class LangChainRetrieverAdapter:
    """Retriever-like adapter over the existing Chroma search function."""

    def __init__(self, search_tool: Any, *, limit: int = 4) -> None:
        self.search_tool = search_tool
        self.limit = limit

    def invoke(self, query: str | dict[str, Any]) -> list[Any]:
        normalized_query = str(query.get("query", "")) if isinstance(query, dict) else str(query)
        return search_results_to_langchain_documents(self.search_tool(normalized_query, self.limit))

    def get_relevant_documents(self, query: str) -> list[Any]:
        return self.invoke(query)


def build_langchain_retriever(search_tool: Any, *, limit: int = 4) -> LangChainRetrieverAdapter:
    """Expose the existing vector search as a LangChain-style retriever."""
    return LangChainRetrieverAdapter(search_tool, limit=limit)


def build_langchain_rag_prompt(
    *,
    system_prompt: str,
    question: str,
    history_block: str,
    context_block: str,
) -> Any:
    """Build a standard LangChain chat prompt, with a serializable fallback."""
    prompt_class = _chat_prompt_template_class()
    if prompt_class is None:
        return {
            "system": system_prompt,
            "user": (
                f"Pregunta: {question}\n\n"
                f"Historial reciente de la conversacion:\n{history_block}\n\n"
                f"Contexto recuperado de PDFs:\n{context_block or 'Sin contexto recuperado.'}"
            ),
        }
    return prompt_class.from_messages(
        [
            ("system", system_prompt),
            (
                "user",
                "Pregunta: {question}\n\n"
                "Historial reciente de la conversacion:\n{history_block}\n\n"
                "Contexto recuperado de PDFs:\n{context_block}",
            ),
        ]
    )


def page_from_langchain_document(document: Any, fallback_page_number: int) -> PDFPage:
    """Normalize a LangChain document-like object back into a PDFPage."""
    if isinstance(document, dict):
        content = str(document.get("page_content", ""))
        metadata = document.get("metadata", {}) or {}
    else:
        content = str(getattr(document, "page_content", ""))
        metadata = getattr(document, "metadata", {}) or {}
    return PDFPage(
        page_number=int(metadata.get("page_number", metadata.get("page", fallback_page_number))),
        text=content,
        extraction_method=str(metadata.get("extraction_method", "langchain")),
    )
