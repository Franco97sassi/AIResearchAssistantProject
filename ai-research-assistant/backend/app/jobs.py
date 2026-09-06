"""Redis-backed background jobs for expensive PDF extraction and indexing."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rq import Queue
    from rq.job import Job

from app.config import (
    JOB_MAX_RETRIES,
    JOB_RETRY_INTERVAL_SECONDS,
    JOB_TIMEOUT_SECONDS,
    REDIS_URL,
)
from app.pdf_loader import extract_text_from_pdf
from app.rag import index_pdf_text


def get_queue() -> Queue:
    from redis import Redis
    from rq import Queue

    return Queue(
        "pdf-indexing", connection=Redis.from_url(REDIS_URL), default_timeout=JOB_TIMEOUT_SECONDS
    )


def build_idempotent_ids(owner_id: str, idempotency_key: str) -> tuple[str, str]:
    """Return stable, non-reversible RQ and document identifiers for one tenant request."""
    digest = sha256(f"{owner_id}:{idempotency_key}".encode()).hexdigest()
    return f"pdf-{digest}", digest


def process_pdf(
    path: str,
    original_filename: str,
    stored_filename: str,
    owner_id: str,
    document_id: str | None = None,
) -> dict[str, Any]:
    """Worker entry point. Arguments are primitives so jobs remain portable."""
    extraction = extract_text_from_pdf(Path(path), use_ocr_fallback=True)
    if extraction.character_count == 0:
        Path(path).unlink(missing_ok=True)
        raise ValueError("No se pudo extraer texto del PDF")
    indexed = index_pdf_text(
        extraction,
        original_filename,
        stored_filename,
        owner_id=owner_id,
        document_id=document_id,
    )
    return {
        "filename": original_filename,
        "stored_filename": stored_filename,
        "page_count": extraction.page_count,
        "character_count": extraction.character_count,
        "document_id": indexed.document_id,
        "chunks_indexed": indexed.chunks_indexed,
        "collection_name": indexed.collection_name,
    }


def enqueue_pdf(
    path: Path,
    original_filename: str,
    stored_filename: str,
    owner_id: str,
    idempotency_key: str | None = None,
) -> Job:
    from rq import Retry
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    queue = get_queue()
    job_id = None
    document_id = None
    if idempotency_key:
        job_id, document_id = build_idempotent_ids(owner_id, idempotency_key)
        try:
            return Job.fetch(job_id, connection=queue.connection)
        except NoSuchJobError:
            pass

    return queue.enqueue(
        process_pdf,
        str(path),
        original_filename,
        stored_filename,
        owner_id,
        document_id,
        job_id=job_id,
        meta={
            "owner_id": owner_id,
            "idempotent": bool(idempotency_key),
            "stored_filename": stored_filename,
        },
        job_timeout=JOB_TIMEOUT_SECONDS,
        retry=Retry(max=JOB_MAX_RETRIES, interval=JOB_RETRY_INTERVAL_SECONDS),
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


def delete_tenant_jobs(owner_id: str) -> dict[str, int]:
    """Cancel queued/retrying jobs and report active jobs that block safe erasure."""
    from rq.registry import ScheduledJobRegistry, StartedJobRegistry

    queue = get_queue()
    started = StartedJobRegistry(queue=queue).get_job_ids()
    active = [fetch_job(job_id) for job_id in started]
    active_count = sum(job_belongs_to(job, owner_id) for job in active)
    if active_count:
        return {"jobs_deleted": 0, "active_jobs": active_count}

    job_ids = {job.id for job in queue.get_jobs()}
    job_ids.update(ScheduledJobRegistry(queue=queue).get_job_ids())
    deleted = 0
    for job_id in job_ids:
        job = fetch_job(job_id)
        if job_belongs_to(job, owner_id):
            job.cancel()
            job.delete()
            deleted += 1
    return {"jobs_deleted": deleted, "active_jobs": 0}
