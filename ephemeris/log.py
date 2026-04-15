"""log.py — Append-only JSONL diagnostic logger for ephemeris ingestion.

Every ingestion phase emits a structured log line to the diagnostic log.
The log is append-only JSONL; one JSON object per line.

Log entry format:
    {
        "ts": "2026-04-15T12:34:56Z",
        "session_id": "abc",
        "phase": "parse|schema|prompt|model|parse_response|write|cleanup|complete",
        "status": "ok|error",
        "message": "...",
        "elapsed_ms": 42   # optional, measured where available
    }

Public API:
    IngestLogger — append-only JSONL logger
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class IngestLogger:
    """Append-only JSONL diagnostic logger.

    Each call to ``log`` appends one JSON line to the configured log file.
    The file and its parent directories are created on first write if absent.

    Args:
        path: Path to the log file. Created on first write if absent.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def log(
        self,
        session_id: str,
        phase: str,
        status: str,
        message: str,
        elapsed_ms: Optional[int] = None,
        pages_written: Optional[list[str]] = None,
    ) -> None:
        """Append a diagnostic log entry.

        Args:
            session_id: The session identifier being processed.
            phase: Pipeline phase name (parse, schema, prompt, model,
                   parse_response, write, cleanup, complete).
            status: Outcome — 'ok' or 'error'.
            message: Human-readable description of the event.
            elapsed_ms: Optional measured elapsed time in milliseconds.
            pages_written: Optional list of relative page paths written,
                           emitted on the ``complete`` phase for SPEC-004.
        """
        entry: dict[str, object] = {
            "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": session_id,
            "phase": phase,
            "status": status,
            "message": message,
        }
        if elapsed_ms is not None:
            entry["elapsed_ms"] = elapsed_ms
        if pages_written is not None:
            entry["pages_written"] = pages_written

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            # Log writes must never crash the ingestion pipeline.
            pass
