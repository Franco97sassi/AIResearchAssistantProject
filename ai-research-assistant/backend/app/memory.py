from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from app.config import HISTORY_DIR

MAX_HISTORY_MESSAGES = 12


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


@dataclass(frozen=True)
class ConversationState:
    session_id: str
    turns: list[ConversationTurn]


def create_session_id() -> str:
    return uuid4().hex


def _session_path(session_id: str) -> Path:
    safe_session_id = "".join(
        character
        for character in session_id
        if character.isalnum() or character in {"-", "_"}
    )
    if not safe_session_id:
        safe_session_id = create_session_id()
    return HISTORY_DIR / f"{safe_session_id}.json"


def load_conversation(session_id: str | None) -> ConversationState:
    normalized_session_id = session_id.strip() if session_id else create_session_id()
    path = _session_path(normalized_session_id)

    if not path.exists():
        return ConversationState(session_id=path.stem, turns=[])

    payload = json.loads(path.read_text(encoding="utf-8"))
    turns = [
        ConversationTurn(
            question=str(item.get("question", "")),
            answer=str(item.get("answer", "")),
        )
        for item in payload.get("turns", [])
        if item.get("question") or item.get("answer")
    ]
    return ConversationState(session_id=path.stem, turns=turns[-MAX_HISTORY_MESSAGES:])


def save_conversation(
    session_id: str, turns: list[ConversationTurn]
) -> ConversationState:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_path(session_id)
    trimmed_turns = turns[-MAX_HISTORY_MESSAGES:]
    payload = {
        "session_id": path.stem,
        "turns": [asdict(turn) for turn in trimmed_turns],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ConversationState(session_id=path.stem, turns=trimmed_turns)


def append_turn(session_id: str, question: str, answer: str) -> ConversationState:
    current_state = load_conversation(session_id)
    updated_turns = [
        *current_state.turns,
        ConversationTurn(question=question, answer=answer),
    ]
    return save_conversation(current_state.session_id, updated_turns)
