from fastapi.testclient import TestClient

import app.main as main
import app.security as security
from app.rag import SearchResult


def test_api_key_authentication_and_tenant_retrieval_scope(monkeypatch):
    monkeypatch.setattr(security, "AUTH_REQUIRED", True)
    monkeypatch.setattr(security, "API_KEY_TENANTS", {"key-a": "tenant-a", "key-b": "tenant-b"})
    observed = []

    def fake_search(**kwargs):
        observed.append(kwargs["owner_id"])
        return [SearchResult("evidence", "a.pdf", 1, "doc", 0.1)]

    monkeypatch.setattr(main, "search_similar_chunks", fake_search)
    client = TestClient(main.app)
    assert client.get("/search", params={"question": "test"}).status_code == 401
    response = client.get("/search", params={"question": "test"}, headers={"X-API-Key": "key-a"})
    assert response.status_code == 200
    assert observed == ["tenant-a"]
    assert response.headers["X-Trace-ID"]


def test_tenant_header_cannot_override_key(monkeypatch):
    monkeypatch.setattr(security, "AUTH_REQUIRED", True)
    monkeypatch.setattr(security, "API_KEY_TENANTS", {"key-a": "tenant-a"})
    response = TestClient(main.app).get(
        "/search",
        params={"question": "test"},
        headers={"X-API-Key": "key-a", "X-Tenant-ID": "tenant-b"},
    )
    assert response.status_code == 403


def test_authenticated_tenant_can_delete_only_its_data(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "AUTH_REQUIRED", True)
    monkeypatch.setattr(security, "API_KEY_TENANTS", {"key-a": "tenant-a"})
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    upload = tmp_path / "safe.pdf"
    upload.write_bytes(b"pdf")
    observed = []
    monkeypatch.setattr(
        main,
        "delete_tenant_jobs",
        lambda tenant: observed.append(("jobs", tenant)) or {"jobs_deleted": 2, "active_jobs": 0},
    )
    monkeypatch.setattr(
        main,
        "delete_tenant_documents",
        lambda tenant: (
            observed.append(("documents", tenant))
            or {"chunks_deleted": 3, "stored_filenames": ["safe.pdf"]}
        ),
    )
    monkeypatch.setattr(
        main,
        "delete_tenant_sessions",
        lambda tenant: observed.append(("sessions", tenant)) or 1,
    )
    monkeypatch.setattr(
        main,
        "delete_tenant_uploads",
        lambda tenant: observed.append(("uploads", tenant)) or upload.unlink() or 1,
    )

    response = TestClient(main.app).delete("/tenants/me/data", headers={"X-API-Key": "key-a"})

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "tenant-a",
        "chunks_deleted": 3,
        "files_deleted": 1,
        "sessions_deleted": 1,
        "jobs_deleted": 2,
    }
    assert observed == [
        ("jobs", "tenant-a"),
        ("documents", "tenant-a"),
        ("uploads", "tenant-a"),
        ("sessions", "tenant-a"),
    ]
    assert not upload.exists()
