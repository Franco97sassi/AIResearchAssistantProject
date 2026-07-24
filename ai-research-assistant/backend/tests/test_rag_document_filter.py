from pathlib import Path

import chromadb

from app.pdf_loader import PDFPage, PDFTextExtractionResult
from app.rag import HashingEmbeddingFunction, index_pdf_text, search_similar_chunks


def create_collection(tmp_path: Path):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return client.get_or_create_collection(
        name="test_document_filter",
        embedding_function=HashingEmbeddingFunction(n_features=64),
    )


def test_search_similar_chunks_can_be_limited_to_one_document(tmp_path):
    collection = create_collection(tmp_path)
    first_document = index_pdf_text(
        PDFTextExtractionResult(
            pages=[
                PDFPage(
                    page_number=1,
                    text="El documento de idiomas describe reglas gramaticales.",
                )
            ]
        ),
        "Reglas Para idiomas.pdf",
        "stored_idiomas.pdf",
        collection=collection,
    )
    second_document = index_pdf_text(
        PDFTextExtractionResult(
            pages=[
                PDFPage(
                    page_number=1,
                    text="El documento metodologico explica entrevistas y analisis cualitativo.",
                )
            ]
        ),
        "Metodologia.pdf",
        "stored_metodologia.pdf",
        collection=collection,
    )

    results = search_similar_chunks(
        "Cual es la metodologia del documento?",
        limit=4,
        document_id=second_document.document_id,
        collection=collection,
    )

    assert results
    assert {result.document_id for result in results} == {second_document.document_id}
    assert first_document.document_id not in {result.document_id for result in results}
