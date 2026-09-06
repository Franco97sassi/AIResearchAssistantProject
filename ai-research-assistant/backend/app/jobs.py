"""Redis-backed background jobs for expensive PDF extraction and indexing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rq import Queue
    from rq.job import Job

from app.config import JOB_TIMEOUT_SECONDS, REDIS_URL
from app.pdf_loader import extract_text_from_pdf
from app.rag import index_pdf_text


def get_queue() -> Queue:
    from redis import Redis
    from rq import Queue

    return Queue(
        "pdf-indexing", connection=Redis.from_url(REDIS_URL), default_timeout=JOB_TIMEOUT_SECONDS
    )


def process_pdf(
    path: str, original_filename: str, stored_filename: str, owner_id: str
) -> dict[str, Any]:
    """Worker entry point. Arguments are primitives so jobs remain portable."""
    extraction = extract_text_from_pdf(Path(path), use_ocr_fallback=True)
    if extraction.character_count == 0:
        Path(path).unlink(missing_ok=True)
        raise ValueError("No se pudo extraer texto del PDF")
    indexed = index_pdf_text(extraction, original_filename, stored_filename, owner_id=owner_id)
    return {
        "filename": original_filename,
        "stored_filename": stored_filename,
        "page_count": extraction.page_count,
        "character_count": extraction.character_count,
        "document_id": indexed.document_id,
        "chunks_indexed": indexed.chunks_indexed,
        "collection_name": indexed.collection_name,
    }


def enqueue_pdf(path: Path, original_filename: str, stored_filename: str, owner_id: str) -> Job:
    return get_queue().enqueue(
        process_pdf,
        str(path),
        original_filename,
        stored_filename,
        owner_id,
        meta={"owner_id": owner_id},
        job_timeout=JOB_TIMEOUT_SECONDS,
        result_ttl=86_400,
        failure_ttl=604_800,
    )


def fetch_job(job_id: str) -> Job:
    from rq.job import Job

    return Job.fetch(job_id, connection=get_queue().connection)


def serialize_job(job: Job) -> dict[str, Any]:
    status = job.get_status(refresh=True)
    payload: dict[str, Any] = {"job_id": job.id, "status": str(status)}
    if job.is_finished:
        payload["result"] = job.result
    if job.is_failed:
        payload["error"] = "El procesamiento fallo. Consulta los logs del worker."
    return payload


def job_belongs_to(job: Job, owner_id: str) -> bool:
    """Prevent a guessed job identifier from crossing tenant boundaries."""
    return str(job.meta.get("owner_id", "")) == owner_id
