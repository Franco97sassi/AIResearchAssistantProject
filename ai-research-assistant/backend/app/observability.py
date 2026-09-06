from __future__ import annotations

import json
import sqlite3
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from app.config import (
    LLM_INPUT_COST_PER_MILLION,
    LLM_OUTPUT_COST_PER_MILLION,
    LOG_DIR,
    METRICS_DB_PATH,
    OTEL_ENABLED,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_SERVICE_NAME,
)


def configure_opentelemetry(app: Any) -> None:
    """Enable standard FastAPI spans and OTLP export when explicitly configured."""
    if not OTEL_ENABLED:
        return

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": OTEL_SERVICE_NAME}))
    exporter = OTLPSpanExporter(
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT or None,
        insecure=OTEL_EXPORTER_OTLP_ENDPOINT.startswith("http://"),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)


_lock = Lock()
current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


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
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_events)")}
        if "trace_id" not in columns:
            connection.execute("ALTER TABLE ai_events ADD COLUMN trace_id TEXT NOT NULL DEFAULT ''")
        if "estimated_cost_usd" not in columns:
            connection.execute(
                "ALTER TABLE ai_events ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0"
            )
        connection.commit()


def log_event(
    event_type: str,
    *,
    latency_ms: float = 0,
    model: str = "",
    source_count: int = 0,
    estimated_tokens: int = 0,
    estimated_output_tokens: int = 0,
    **metadata: Any,
) -> None:
    """Persist one local AI event for demos without paid observability services."""
    init_observability()
    with _lock, sqlite3.connect(METRICS_DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO ai_events (
                created_at, event_type, latency_ms, model,
                source_count, estimated_tokens, metadata, trace_id, estimated_cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_now(),
                event_type,
                float(latency_ms or 0),
                model or "",
                int(source_count or 0),
                int(estimated_tokens or 0),
                json.dumps(metadata, ensure_ascii=False, default=str),
                current_trace_id.get(),
                (
                    int(estimated_tokens or 0) * LLM_INPUT_COST_PER_MILLION
                    + int(estimated_output_tokens or 0) * LLM_OUTPUT_COST_PER_MILLION
                )
                / 1_000_000,
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
                , COALESCE(SUM(estimated_cost_usd), 0) AS total_estimated_cost_usd
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
            SELECT created_at, event_type, latency_ms, model, source_count, estimated_tokens, metadata, trace_id
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
        "total_estimated_cost_usd": round(float(totals["total_estimated_cost_usd"]), 8),
        "events_by_type": [dict(row) for row in by_type],
        "recent_events": [
            {
                **{key: row[key] for key in row.keys() if key != "metadata"},
                "metadata": json.loads(row["metadata"] or "{}"),
            }
            for row in recent
        ],
    }


def prometheus_metrics() -> str:
    """Render dependency-free Prometheus metrics for scraping and alerting."""
    values = collect_metrics()
    lines = [
        "# HELP ai_events_total Total recorded application events.",
        "# TYPE ai_events_total counter",
        f"ai_events_total {values['event_count']}",
        "# HELP ai_request_latency_milliseconds Average observed latency.",
        "# TYPE ai_request_latency_milliseconds gauge",
        f"ai_request_latency_milliseconds {values['average_latency_ms']}",
        "# HELP ai_estimated_tokens_total Estimated prompt tokens.",
        "# TYPE ai_estimated_tokens_total counter",
        f"ai_estimated_tokens_total {values['total_estimated_tokens']}",
        "# HELP ai_estimated_cost_usd_total Estimated model spend in USD.",
        "# TYPE ai_estimated_cost_usd_total counter",
        f"ai_estimated_cost_usd_total {values['total_estimated_cost_usd']}",
    ]
    for event in values["events_by_type"]:
        event_type = str(event["event_type"]).replace('"', "")
        lines.append(f'ai_events_by_type_total{{event_type="{event_type}"}} {event["count"]}')
    return "\n".join(lines) + "\n"


def get_trace(trace_id: str) -> list[dict[str, Any]]:
    """Return all spans/events for one request trace."""
    init_observability()
    with _lock, sqlite3.connect(METRICS_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT created_at, event_type, latency_ms, model, source_count, "
            "estimated_tokens, metadata, trace_id FROM ai_events WHERE trace_id = ? ORDER BY id",
            (trace_id,),
        ).fetchall()
    return [{**dict(row), "metadata": json.loads(row["metadata"] or "{}")} for row in rows]
