from app import chat_history


def test_append_chat_exchange_persists_session(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_history, "CHAT_HISTORY_PATH", tmp_path / "history.json")

    session = chat_history.append_chat_exchange(
        session_id="session-1",
        question="What is RAG?",
        answer="RAG combines retrieval and generation.",
        model="test-model",
        used_llm=False,
        sources=[{"filename": "paper.pdf", "page_number": 1}],
    )

    loaded_session = chat_history.get_session("session-1")
    summaries = chat_history.list_sessions()

    assert session["session_id"] == "session-1"
    assert loaded_session["messages"][0]["question"] == "What is RAG?"
    assert loaded_session["messages"][0]["sources"][0]["filename"] == "paper.pdf"
    assert summaries[0]["session_id"] == "session-1"
    assert summaries[0]["message_count"] == 1


def test_build_retrieval_query_includes_recent_memory():
    query = chat_history.build_retrieval_query(
        "What does that imply?",
        [
            {
                "question": "What is vector search?",
                "answer": "It finds semantically similar chunks.",
            }
        ],
    )

    assert "What is vector search?" in query
    assert "semantically similar chunks" in query
    assert "What does that imply?" in query


def test_delete_tenant_sessions_keeps_other_tenants(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_history, "CHAT_HISTORY_PATH", tmp_path / "history.json")
    for tenant in ("tenant-a", "tenant-b"):
        chat_history.append_chat_exchange(
            session_id=f"{tenant}:session-1",
            question="Question",
            answer="Answer",
            model="local",
            used_llm=False,
            sources=[],
        )

    assert chat_history.delete_tenant_sessions("tenant-a") == 1
    assert [item["session_id"] for item in chat_history.list_sessions()] == ["tenant-b:session-1"]
