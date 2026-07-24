from fastapi.testclient import TestClient

import app.main as main


def test_cors_headers_are_sent_for_agent_errors(monkeypatch):
    def failing_agent(**kwargs):
        raise RuntimeError("simulated agent failure")

    monkeypatch.setattr(main, "run_research_agent", failing_agent)
    client = TestClient(main.app, raise_server_exceptions=False)

    response = client.post(
        "/agent/chat",
        headers={"Origin": "http://localhost:5173"},
        json={
            "question": "Que dice el documento?",
            "session_id": "cors-test",
            "limit": 4,
        },
    )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_allows_frontend_agent_chat():
    client = TestClient(main.app)

    response = client.options(
        "/agent/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
