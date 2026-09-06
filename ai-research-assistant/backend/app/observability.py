from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from app.config import LOG_DIR, METRICS_DB_PATH

_lock = Lock()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def init_observability() -> None:
    """Create the local metrics store used for lightweight AI monitoring."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, sqlite3.connect(METRICS_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                latency_ms REAL NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT '',
                source_count INTEGER NOT NULL DEFAULT 0,
                estimated_tokens INTEGER NOT NULL DEFAULT 0,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        connection.commit()


def log_event(
    event_type: str,
    *,
    latency_ms: float = 0,
    model: str = "",
    source_count: int = 0,
    estimated_tokens: int = 0,
    **metadata: Any,
) -> None:
    """Persist one local AI event for demos without paid observability services."""
    init_observability()
    with _lock, sqlite3.connect(METRICS_DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO ai_events (
                created_at, event_type, latency_ms, model,
                source_count, estimated_tokens, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_now(),
                event_type,
                float(latency_ms or 0),
                model or "",
                int(source_count or 0),
                int(estimated_tokens or 0),
                json.dumps(metadata, ensure_ascii=False, default=str),
            ),
        )
        connection.commit()


def collect_metrics() -> dict[str, Any]:
    """Return compact AI metrics for monitoring, demos, and frontend checks."""
    init_observability()
    with _lock, sqlite3.connect(METRICS_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS event_count,
                COALESCE(AVG(latency_ms), 0) AS average_latency_ms,
                COALESCE(SUM(estimated_tokens), 0) AS total_estimated_tokens,
                COALESCE(AVG(source_count), 0) AS average_source_count
            FROM ai_events
            """
        ).fetchone()
        by_type = connection.execute(
            """
            SELECT event_type, COUNT(*) AS count
            FROM ai_events
            GROUP BY event_type
            ORDER BY count DESC, event_type ASC
            """
        ).fetchall()
        recent = connection.execute(
            """
            SELECT created_at, event_type, latency_ms, model, source_count, estimated_tokens, metadata
            FROM ai_events
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

    return {
        "event_count": int(totals["event_count"]),
        "average_latency_ms": round(float(totals["average_latency_ms"]), 2),
        "total_estimated_tokens": int(totals["total_estimated_tokens"]),
        "average_source_count": round(float(totals["average_source_count"]), 2),
        "events_by_type": [dict(row) for row in by_type],
        "recent_events": [
            {
                **{key: row[key] for key in row.keys() if key != "metadata"},
                "metadata": json.loads(row["metadata"] or "{}"),
            }
            for row in recent
        ],
    }
