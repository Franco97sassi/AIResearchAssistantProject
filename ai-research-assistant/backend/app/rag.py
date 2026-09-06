from dataclasses import dataclass
from typing import TypedDict
from uuid import uuid4

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_DIR,
    EMBEDDING_PROVIDER,
    HASHING_EMBEDDING_FEATURES,
    RERANKER_MODEL,
    RERANKING_ENABLED,
    RETRIEVAL_MODE,
    SENTENCE_TRANSFORMER_MODEL,
)
from app.langchain_rag import build_langchain_documents, split_text_with_langchain
from app.pdf_loader import PDFTextExtractionResult


@dataclass(frozen=True)
class TextChunk:
    text: str
    page_number: int
    chunk_index: int


@dataclass(frozen=True)
class IndexingResult:
    document_id: str
    filename: str
    chunks_indexed: int
    collection_name: str


@dataclass(frozen=True)
class IndexedDocument:
    document_id: str
    filename: str
    stored_filename: str
    chunk_count: int


@dataclass(frozen=True)
class SearchResult:
    text: str
    filename: str
    page_number: int
    document_id: str
    distance: float | None


class TenantDocumentDeletion(TypedDict):
    chunks_deleted: int
    stored_filenames: list[str]


class HashingEmbeddingFunction(EmbeddingFunction[Documents]):
    """Offline embedding function compatible with ChromaDB.

    It keeps the project free and runnable without downloading a model during
    tests. Use EMBEDDING_PROVIDER=sentence-transformers when you want stronger
    semantic retrieval with a local Sentence Transformers model.
    """

    def __init__(self, n_features: int = 384):
        self.vectorizer = HashingVectorizer(
            n_features=n_features,
            alternate_sign=False,
            norm="l2",
            ngram_range=(1, 2),
        )

    def __call__(self, input: Documents) -> Embeddings:
        return self.vectorizer.transform(input).toarray().astype(float).tolist()

    @staticmethod
    def name() -> str:
        return "hashing_vectorizer"

    @staticmethod
    def build_from_config(config: dict[str, int]) -> "HashingEmbeddingFunction":
        return HashingEmbeddingFunction(n_features=config.get("n_features", 384))

    def get_config(self) -> dict[str, int]:
        return {"n_features": self.vectorizer.n_features}


class SentenceTransformerEmbeddingFunction(EmbeddingFunction[Documents]):
    """Semantic embedding function powered by Sentence Transformers."""

    def __init__(self, model_name: str = SENTENCE_TRANSFORMER_MODEL):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> Embeddings:
        return self.model.encode(list(input), normalize_embeddings=True).tolist()

    @staticmethod
    def name() -> str:
        return "sentence_transformer"

    @staticmethod
    def build_from_config(
        config: dict[str, str],
    ) -> "SentenceTransformerEmbeddingFunction":
        return SentenceTransformerEmbeddingFunction(
            model_name=config.get("model_name", SENTENCE_TRANSFORMER_MODEL)
        )

    def get_config(self) -> dict[str, str]:
        return {"model_name": self.model_name}


def build_embedding_function() -> EmbeddingFunction[Documents]:
    """Build the configured embedding provider for ChromaDB."""
    if EMBEDDING_PROVIDER == "hashing":
        return HashingEmbeddingFunction(n_features=HASHING_EMBEDDING_FEATURES)
    if EMBEDDING_PROVIDER in {"sentence-transformers", "sentence_transformers"}:
        return SentenceTransformerEmbeddingFunction(model_name=SENTENCE_TRANSFORMER_MODEL)

    raise ValueError("EMBEDDING_PROVIDER debe ser 'hashing' o 'sentence-transformers'")


_embedding_function = build_embedding_function()
_client: chromadb.ClientAPI | None = None
_collection: Collection | None = None


def chunk_pdf_text(
    extraction_result: PDFTextExtractionResult,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> list[TextChunk]:
    """Split extracted PDF pages into overlapping chunks for retrieval."""
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap debe ser menor que chunk_size")

    chunks: list[TextChunk] = []
    langchain_documents = build_langchain_documents(extraction_result, filename="extracted-pdf")
    for document_index, document in enumerate(langchain_documents):
        raw_text = (
            document.get("page_content", "")
            if isinstance(document, dict)
            else document.page_content
        )
        page_text = " ".join(str(raw_text).split())
        if not page_text:
            continue
        metadata = document.get("metadata", {}) if isinstance(document, dict) else document.metadata
        page_number = int(metadata.get("page_number", metadata.get("page", document_index + 1)))
        langchain_chunks = split_text_with_langchain(
            page_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        if langchain_chunks is not None:
            chunks.extend(
                TextChunk(
                    text=chunk_text.strip(),
                    page_number=page_number,
                    chunk_index=chunk_index,
                )
                for chunk_index, chunk_text in enumerate(langchain_chunks)
                if chunk_text.strip()
            )
            continue
        start = 0
        page_chunk_index = 0
        while start < len(page_text):
            end = min(start + chunk_size, len(page_text))
            chunk_text = page_text[start:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        page_number=page_number,
                        chunk_index=page_chunk_index,
                    )
                )
            if end == len(page_text):
                break
            start = end - chunk_overlap
            page_chunk_index += 1

    return chunks


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def get_collection() -> Collection:
    global _collection
    if _collection is None:
        _collection = get_chroma_client().get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            embedding_function=_embedding_function,
            metadata={"description": "PDF chunks for the AI Research Assistant"},
        )
    return _collection


def index_pdf_text(
    extraction_result: PDFTextExtractionResult,
    filename: str,
    stored_filename: str,
    collection: Collection | None = None,
    owner_id: str = "public",
    chunk_size: int = 900,
    chunk_overlap: int = 150,
    document_id: str | None = None,
) -> IndexingResult:
    """Store PDF chunks in ChromaDB so they can be retrieved by questions."""
    chunks = chunk_pdf_text(extraction_result, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    document_id = document_id or uuid4().hex
    target_collection = collection or get_collection()

    if chunks:
        # ``upsert`` makes a retried asynchronous job safe after a worker dies
        # between writing vectors and reporting completion.
        target_collection.upsert(
            ids=[f"{document_id}:{chunk.page_number}:{chunk.chunk_index}" for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "document_id": document_id,
                    "filename": filename,
                    "stored_filename": stored_filename,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "owner_id": owner_id,
                }
                for chunk in chunks
            ],
        )

    return IndexingResult(
        document_id=document_id,
        filename=filename,
        chunks_indexed=len(chunks),
        collection_name=target_collection.name,
    )


def delete_tenant_documents(
    owner_id: str, collection: Collection | None = None
) -> TenantDocumentDeletion:
    """Delete every vector owned by a tenant and return its upload filenames."""
    target_collection = collection or get_collection()
    stored = target_collection.get(where={"owner_id": owner_id}, include=["metadatas"])
    ids = [str(item) for item in stored.get("ids", [])]
    stored_filenames = sorted(
        {
            str(metadata.get("stored_filename", ""))
            for metadata in stored.get("metadatas", [])
            if metadata and metadata.get("stored_filename")
        }
    )
    if ids:
        target_collection.delete(ids=ids)
    return {"chunks_deleted": len(ids), "stored_filenames": stored_filenames}


def _result_key(result: SearchResult) -> tuple[str, int, str]:
    return (result.document_id, result.page_number, result.text[:80])


def _build_document_filter(
    document_id: str | None, owner_id: str | None = None
) -> dict[str, object] | None:
    normalized_document_id = (document_id or "").strip()
    clauses: list[dict[str, object]] = []
    if normalized_document_id:
        clauses.append({"document_id": normalized_document_id})
    if owner_id:
        clauses.append({"owner_id": owner_id})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses} if clauses else None


def _dense_search(
    question: str,
    limit: int,
    collection: Collection,
    document_id: str | None = None,
    owner_id: str | None = None,
) -> list[SearchResult]:
    where = _build_document_filter(document_id, owner_id)
    query_kwargs = {"query_texts": [question], "n_results": limit}
    if where is not None:
        query_kwargs["where"] = where
    results = collection.query(**query_kwargs)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    return [
        SearchResult(
            text=document,
            filename=str(metadata.get("filename", "")),
            page_number=int(metadata.get("page_number", 0)),
            document_id=str(metadata.get("document_id", "")),
            distance=float(distance) if distance is not None else None,
        )
        for document, metadata, distance in zip(documents, metadatas, distances, strict=False)
    ]


def _bm25_search(
    question: str,
    limit: int,
    collection: Collection,
    document_id: str | None = None,
    owner_id: str | None = None,
) -> list[SearchResult]:
    where = _build_document_filter(document_id, owner_id)
    get_kwargs = {"include": ["documents", "metadatas"]}
    if where is not None:
        get_kwargs["where"] = where
    stored = collection.get(**get_kwargs)
    documents = stored.get("documents", [])
    metadatas = stored.get("metadatas", [])
    if not documents:
        return []
    vectorizer = TfidfVectorizer(stop_words=None, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(documents)
    scores = cosine_similarity(vectorizer.transform([question]), matrix).ravel()
    ranked = scores.argsort()[::-1][:limit]
    output: list[SearchResult] = []
    for index in ranked:
        metadata = metadatas[index] or {}
        output.append(
            SearchResult(
                text=documents[index],
                filename=str(metadata.get("filename", "")),
                page_number=int(metadata.get("page_number", 0)),
                document_id=str(metadata.get("document_id", "")),
                distance=float(1 - scores[index]),
            )
        )
    return output


def _rerank(question: str, results: list[SearchResult], limit: int) -> list[SearchResult]:
    if not RERANKING_ENABLED or not results:
        return results[:limit]
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(RERANKER_MODEL)
        scores = model.predict([(question, result.text) for result in results])
        return [
            result
            for _, result in sorted(
                zip(scores, results, strict=False), key=lambda item: item[0], reverse=True
            )
        ][:limit]
    except Exception:
        return results[:limit]


def search_similar_chunks(
    question: str,
    limit: int = 4,
    document_id: str | None = None,
    collection: Collection | None = None,
    owner_id: str | None = None,
) -> list[SearchResult]:
    """Find relevant chunks using dense, BM25, or hybrid retrieval plus optional reranking."""
    normalized_question = question.strip()
    if not normalized_question:
        return []
    target_collection = collection or get_collection()
    mode = RETRIEVAL_MODE if RETRIEVAL_MODE in {"dense", "bm25", "hybrid"} else "dense"
    if mode == "bm25":
        return _rerank(
            normalized_question,
            _bm25_search(normalized_question, limit * 3, target_collection, document_id, owner_id),
            limit,
        )
    if mode == "hybrid":
        merged: dict[tuple[str, int, str], SearchResult] = {}
        for result in _dense_search(
            normalized_question, limit * 3, target_collection, document_id, owner_id
        ) + _bm25_search(normalized_question, limit * 3, target_collection, document_id, owner_id):
            merged.setdefault(_result_key(result), result)
        return _rerank(normalized_question, list(merged.values()), limit)
    return _rerank(
        normalized_question,
        _dense_search(normalized_question, limit * 3, target_collection, document_id, owner_id),
        limit,
    )


def list_indexed_documents(collection: Collection | None = None) -> list[dict[str, object]]:
    """Return a compact inventory of PDF documents stored in ChromaDB."""
    target_collection = collection or get_collection()
    stored_chunks = target_collection.get(include=["metadatas"])
    documents: dict[str, IndexedDocument] = {}

    for metadata in stored_chunks.get("metadatas", []):
        if not metadata:
            continue

        document_id = str(metadata.get("document_id", ""))
        if not document_id:
            continue

        existing = documents.get(document_id)
        documents[document_id] = IndexedDocument(
            document_id=document_id,
            filename=str(metadata.get("filename", "")),
            stored_filename=str(metadata.get("stored_filename", "")),
            chunk_count=(existing.chunk_count if existing else 0) + 1,
        )

    return [
        {
            "document_id": document.document_id,
            "filename": document.filename,
            "stored_filename": document.stored_filename,
            "chunk_count": document.chunk_count,
        }
        for document in sorted(documents.values(), key=lambda item: item.filename)
    ]
