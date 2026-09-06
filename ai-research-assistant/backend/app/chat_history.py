from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.config import CHAT_HISTORY_PATH

MAX_MEMORY_EXCHANGES = 6

_lock = Lock()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def create_session_id() -> str:
    return uuid4().hex


def normalize_session_id(session_id: str | None) -> str:
    normalized = (session_id or "").strip()
    return normalized or create_session_id()


def _empty_store() -> dict[str, dict[str, object]]:
    return {"sessions": {}}


def _load_store(path: Path | None = None) -> dict[str, dict[str, object]]:
    history_path = path or CHAT_HISTORY_PATH
    if not history_path.exists():
        return _empty_store()

    with history_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
        return _empty_store()

    return data


def _save_store(store: dict[str, dict[str, object]], path: Path | None = None) -> None:
    history_path = path or CHAT_HISTORY_PATH
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("w", encoding="utf-8") as file:
        json.dump(store, file, ensure_ascii=False, indent=2)


def _new_session(session_id: str) -> dict[str, object]:
    timestamp = _utc_now()
    return {
        "session_id": session_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "messages": [],
    }


def get_session(session_id: str) -> dict[str, object]:
    with _lock:
        store = _load_store()
        session = store["sessions"].get(session_id)
        if isinstance(session, dict):
            return session
        return _new_session(session_id)


def list_sessions() -> list[dict[str, object]]:
    with _lock:
        store = _load_store()
        sessions = []

        for session in store["sessions"].values():
            if not isinstance(session, dict):
                continue
            messages = session.get("messages", [])
            if not isinstance(messages, list):
                messages = []
            last_message = messages[-1] if messages else {}
            sessions.append(
                {
                    "session_id": session.get("session_id", ""),
                    "created_at": session.get("created_at", ""),
                    "updated_at": session.get("updated_at", ""),
                    "message_count": len(messages),
                    "last_question": last_message.get("question", "")
                    if isinstance(last_message, dict)
                    else "",
                }
            )

        return sorted(sessions, key=lambda item: str(item["updated_at"]), reverse=True)


def delete_tenant_sessions(tenant_id: str) -> int:
    """Delete sessions whose server-side key is scoped to ``tenant_id``."""
    prefix = f"{tenant_id}:"
    with _lock:
        store = _load_store()
        session_ids = [key for key in store["sessions"] if key.startswith(prefix)]
        for session_id in session_ids:
            del store["sessions"][session_id]
        if session_ids:
            _save_store(store)
        return len(session_ids)


def get_recent_history(session_id: str, limit: int = MAX_MEMORY_EXCHANGES) -> list[dict]:
    session = get_session(session_id)
    messages = session.get("messages", [])
    if not isinstance(messages, list):
        return []
    return messages[-limit:]


def filter_history_for_document(
    history: list[dict],
    document_id: str | None,
) -> list[dict]:
    """Keep memory scoped to the active document when a document filter is used."""
    normalized_document_id = (document_id or "").strip()
    if not normalized_document_id:
        return history

    scoped_history = []
    for message in history:
        sources = message.get("sources", [])
        if not isinstance(sources, list) or not sources:
            scoped_history.append(message)
            continue

        if any(
            isinstance(source, dict)
            and str(source.get("document_id", "")).strip() == normalized_document_id
            for source in sources
        ):
            scoped_history.append(message)

    return scoped_history


def append_chat_exchange(
    *,
    session_id: str,
    question: str,
    answer: str,
    model: str,
    used_llm: bool,
    sources: list[dict[str, object]],
    agent_steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    with _lock:
        store = _load_store()
        session = store["sessions"].get(session_id)
        if not isinstance(session, dict):
            session = _new_session(session_id)

        messages = session.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        timestamp = _utc_now()
        messages.append(
            {
                "id": uuid4().hex,
                "question": question,
                "answer": answer,
                "model": model,
                "used_llm": used_llm,
                "sources": sources,
                "agent_steps": agent_steps or [],
                "created_at": timestamp,
            }
        )
        session["messages"] = messages
        session["updated_at"] = timestamp
        store["sessions"][session_id] = session
        _save_store(store)
        return session


def build_retrieval_query(question: str, history: list[dict]) -> str:
    if not history:
        return question

    recent_turns = []
    for message in history[-3:]:
        recent_turns.append(str(message.get("question", "")))
        recent_turns.append(str(message.get("answer", ""))[:500])

    return "\n".join([*recent_turns, question])
