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
