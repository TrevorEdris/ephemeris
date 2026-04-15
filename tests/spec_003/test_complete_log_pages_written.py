"""test_complete_log_pages_written.py — SPEC-003/SPEC-004 M1 log format tests.

Verifies that the complete-phase log entry includes a structured
``pages_written`` field listing relative page paths.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _make_fake_response(operations: list[dict]) -> str:  # type: ignore[type-arg]
    return json.dumps({"operations": operations})


def _copy_fixture(name: str, tmp_path: Path, session_id: str) -> Path:
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / f"{session_id}.jsonl"
    shutil.copy(FIXTURES / name, dest)
    return dest


def _read_log_entries(log_path: Path) -> list[dict]:  # type: ignore[type-arg]
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


class TestCompleteLogPagesWritten:
    """complete-phase log entry must carry pages_written list."""

    def test_complete_log_has_pages_written(self, tmp_path: Path) -> None:
        """After ingest_one writes N pages, complete entry has pages_written of length N."""
        from ephemeris.ingest import ingest_one
        from ephemeris.log import IngestLogger
        from ephemeris.model import FakeModelClient

        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        log_path = tmp_path / "ephemeris.log"
        logger = IngestLogger(log_path)
        session_id = "m1-session-001"

        transcript_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

        operations = [
            {
                "action": "create",
                "page_type": "topic",
                "page_name": "error-handling-strategy",
                "content": {"overview": "typed subclasses", "details": ""},
                "cross_references": [],
            },
            {
                "action": "create",
                "page_type": "entity",
                "page_name": "AppError",
                "content": {"role": "Base exception class", "relationships": []},
                "cross_references": [],
            },
        ]
        model = FakeModelClient(response=_make_fake_response(operations))

        result = ingest_one(
            transcript_path=transcript_path,
            wiki_root=wiki_root,
            model=model,
            log=logger,
            session_id=session_id,
            session_date="2026-04-15",
        )

        assert result.success
        entries = _read_log_entries(log_path)

        complete_entries = [
            e for e in entries
            if e.get("session_id") == session_id and e.get("phase") == "complete"
        ]
        assert len(complete_entries) == 1, (
            f"Expected 1 complete entry for {session_id}, got {len(complete_entries)}"
        )
        complete = complete_entries[0]

        assert "pages_written" in complete, (
            f"complete log entry missing 'pages_written': {complete}"
        )
        pages = complete["pages_written"]
        assert isinstance(pages, list)
        assert len(pages) == 2, f"Expected 2 pages_written, got {len(pages)}: {pages}"

        # Paths must be relative (no absolute paths)
        for p in pages:
            assert not Path(p).is_absolute(), f"pages_written entry is absolute: {p}"

        # Must contain both expected relative paths
        assert any("error-handling-strategy" in p for p in pages)
        assert any("AppError" in p for p in pages)

    def test_complete_log_empty_pages_written_for_no_ops(self, tmp_path: Path) -> None:
        """When no operations are extracted, pages_written should be empty list."""
        from ephemeris.ingest import ingest_one
        from ephemeris.log import IngestLogger
        from ephemeris.model import FakeModelClient

        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        log_path = tmp_path / "ephemeris.log"
        logger = IngestLogger(log_path)
        session_id = "m1-session-002"

        transcript_path = _copy_fixture("transcript_empty.jsonl", tmp_path, session_id)
        model = FakeModelClient(response=_make_fake_response([]))

        result = ingest_one(
            transcript_path=transcript_path,
            wiki_root=wiki_root,
            model=model,
            log=logger,
            session_id=session_id,
            session_date="2026-04-15",
        )

        assert result.success
        entries = _read_log_entries(log_path)
        complete_entries = [
            e for e in entries
            if e.get("session_id") == session_id and e.get("phase") == "complete"
        ]
        assert len(complete_entries) == 1
        complete = complete_entries[0]
        assert "pages_written" in complete
        assert complete["pages_written"] == []
