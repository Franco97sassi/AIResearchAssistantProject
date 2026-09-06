from fastapi.testclient import TestClient

import app.main as main


def test_upload_requires_a_file():
    response = TestClient(main.app).post("/upload-pdf")

    assert response.status_code == 422


def test_upload_rejects_non_pdf_file():
    response = TestClient(main.app).post(
        "/upload-pdf",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Solo se permiten archivos PDF."


def test_upload_rejects_file_larger_than_configured_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(main, "MAX_UPLOAD_SIZE_BYTES", 4)
    monkeypatch.setattr(main, "MAX_UPLOAD_SIZE_MB", 0)

    response = TestClient(main.app).post(
        "/upload-pdf",
        files={"file": ("large.pdf", b"%PDF-too-large", "application/pdf")},
    )

    assert response.status_code == 413
    assert not list(tmp_path.iterdir())


def test_chat_rejects_empty_question():
    response = TestClient(main.app).post("/chat", json={"question": ""})

    assert response.status_code == 422


def test_search_rejects_limit_outside_contract():
    response = TestClient(main.app).get(
        "/search",
        params={"question": "RAG", "limit": 11},
    )

    assert response.status_code == 422
