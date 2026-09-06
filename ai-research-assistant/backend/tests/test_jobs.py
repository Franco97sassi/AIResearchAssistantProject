from pathlib import Path
from types import SimpleNamespace

from app import jobs


def test_process_pdf_indexes_extracted_content(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    extraction = SimpleNamespace(character_count=10, page_count=2)
    indexed = SimpleNamespace(document_id="doc-1", chunks_indexed=3, collection_name="papers")
    monkeypatch.setattr(jobs, "extract_text_from_pdf", lambda *_args, **_kwargs: extraction)
    monkeypatch.setattr(jobs, "index_pdf_text", lambda *_args, **_kwargs: indexed)

    result = jobs.process_pdf(str(pdf), "paper.pdf", "safe.pdf", "tenant-a")

    assert result["document_id"] == "doc-1"
    assert result["chunks_indexed"] == 3


def test_serialize_failed_job_hides_internal_error():
    job = SimpleNamespace(
        id="job-1",
        get_status=lambda refresh: "failed",
        is_finished=False,
        is_failed=True,
    )

    payload = jobs.serialize_job(job)

    assert payload == {
        "job_id": "job-1",
        "status": "failed",
        "error": "El procesamiento fallo. Consulta los logs del worker.",
    }


def test_job_owner_isolated_by_tenant():
    job = SimpleNamespace(meta={"owner_id": "tenant-a"})
    assert jobs.job_belongs_to(job, "tenant-a") is True
    assert jobs.job_belongs_to(job, "tenant-b") is False
