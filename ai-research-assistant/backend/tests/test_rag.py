from pathlib import Path

import chromadb

from app.pdf_loader import PDFPage, PDFTextExtractionResult
from app.rag import (
    HashingEmbeddingFunction,
    chunk_pdf_text,
    index_pdf_text,
    list_indexed_documents,
    search_similar_chunks,
)


def create_collection(tmp_path: Path):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return client.get_or_create_collection(
        name="test_research_papers",
        embedding_function=HashingEmbeddingFunction(n_features=64),
    )


def test_chunk_pdf_text_creates_overlapping_chunks():
    extraction = PDFTextExtractionResult(
        pages=[
            PDFPage(page_number=1, text="abcdefghij"),
            PDFPage(page_number=2, text="klmno"),
        ]
    )

    chunks = chunk_pdf_text(extraction, chunk_size=6, chunk_overlap=2)

    assert [chunk.text for chunk in chunks] == ["abcdef", "efghij", "klmno"]
    assert [chunk.page_number for chunk in chunks] == [1, 1, 2]


def test_index_pdf_text_stores_chunks_with_metadata(tmp_path):
    collection = create_collection(tmp_path)
    extraction = PDFTextExtractionResult(
        pages=[PDFPage(page_number=3, text="Vector databases store embeddings for RAG demos.")]
    )

    result = index_pdf_text(
        extraction_result=extraction,
        filename="paper.pdf",
        stored_filename="stored_paper.pdf",
        collection=collection,
    )

    stored = collection.get(include=["documents", "metadatas"])
    assert result.chunks_indexed == 1
    assert result.collection_name == "test_research_papers"
    assert stored["documents"] == ["Vector databases store embeddings for RAG demos."]
    assert stored["metadatas"][0]["filename"] == "paper.pdf"
    assert stored["metadatas"][0]["page_number"] == 3


def test_search_similar_chunks_returns_relevant_context(tmp_path):
    collection = create_collection(tmp_path)
    extraction = PDFTextExtractionResult(
        pages=[
            PDFPage(page_number=1, text="Bananas and apples are fruits."),
            PDFPage(page_number=2, text="Chroma stores vector embeddings for retrieval."),
        ]
    )
    index_pdf_text(extraction, "notes.pdf", "stored_notes.pdf", collection=collection)

    results = search_similar_chunks(
        "How are vector embeddings stored?", limit=1, collection=collection
    )

    assert len(results) == 1
    assert "embeddings" in results[0].text
    assert results[0].filename == "notes.pdf"
    assert results[0].page_number == 2


def test_list_indexed_documents_groups_chunks_by_pdf(tmp_path):
    collection = create_collection(tmp_path)
    extraction = PDFTextExtractionResult(
        pages=[
            PDFPage(page_number=1, text="A" * 1000),
            PDFPage(page_number=2, text="B" * 1000),
        ]
    )
    result = index_pdf_text(
        extraction,
        "manual.pdf",
        "stored_manual.pdf",
        collection=collection,
    )

    documents = list_indexed_documents(collection=collection)

    assert documents == [
        {
            "document_id": result.document_id,
            "filename": "manual.pdf",
            "stored_filename": "stored_manual.pdf",
            "chunk_count": result.chunks_indexed,
        }
    ]
