"""test_transcript_malformed.py — SPEC-003 M2 malformed JSONL visibility tests.

Verifies that load_transcript surfaces a skipped-line count and raises
TranscriptParseError when every non-empty line is malformed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class TestSkippedLineCount:
    """load_transcript must return a skipped count alongside messages."""

    def test_skipped_count_matches_malformed_lines(self, tmp_path: Path) -> None:
        from ephemeris.transcript import load_transcript

        jsonl = tmp_path / "t.jsonl"
        jsonl.write_text(
            "NOT JSON AT ALL\n"
            '{"type": "user", "content": "valid"}\n'
            "[1, 2, 3]\n",
            encoding="utf-8",
        )

        result = load_transcript(jsonl)
        # result must expose skipped_lines count
        assert hasattr(result, "skipped_lines"), (
            "load_transcript must return an object with skipped_lines attribute"
        )
        assert result.skipped_lines == 2

    def test_skipped_count_zero_for_clean_file(self, tmp_path: Path) -> None:
        from ephemeris.transcript import load_transcript

        jsonl = tmp_path / "t.jsonl"
        jsonl.write_text(
            '{"type": "user", "content": "hello"}\n'
            '{"type": "assistant", "content": "hi"}\n',
            encoding="utf-8",
        )

        result = load_transcript(jsonl)
        assert result.skipped_lines == 0

    def test_messages_still_returned_with_skipped(self, tmp_path: Path) -> None:
        from ephemeris.transcript import load_transcript

        jsonl = tmp_path / "t.jsonl"
        jsonl.write_text(
            "GARBAGE\n"
            '{"type": "user", "content": "valid"}\n',
            encoding="utf-8",
        )

        result = load_transcript(jsonl)
        assert len(result.messages) == 1
        assert result.messages[0].content == "valid"
        assert result.skipped_lines == 1


class TestAllMalformedRaises:
    """When every non-empty line is malformed, raise TranscriptParseError."""

    def test_all_malformed_raises(self, tmp_path: Path) -> None:
        from ephemeris.exceptions import TranscriptParseError
        from ephemeris.transcript import load_transcript

        jsonl = tmp_path / "t.jsonl"
        jsonl.write_text(
            "NOT JSON\n"
            "ALSO NOT JSON\n"
            "[1, 2, 3]\n",
            encoding="utf-8",
        )

        with pytest.raises(TranscriptParseError):
            load_transcript(jsonl)

    def test_empty_file_does_not_raise(self, tmp_path: Path) -> None:
        """Empty file is not the same as all-malformed — returns empty result."""
        from ephemeris.transcript import load_transcript

        jsonl = tmp_path / "t.jsonl"
        jsonl.write_text("", encoding="utf-8")

        result = load_transcript(jsonl)
        assert result.messages == []
        assert result.skipped_lines == 0


class TestIngestLogsSkippedWarning:
    """ingest_one logs a parse warning when skipped_lines > 0."""

    def _copy_fixture(self, name: str, tmp_path: Path, session_id: str) -> Path:
        staging = tmp_path / "staging" / "session-end"
        staging.mkdir(parents=True, exist_ok=True)
        dest = staging / f"{session_id}.jsonl"
        shutil.copy(FIXTURES / name, dest)
        return dest

    def _write_malformed_transcript(self, tmp_path: Path, session_id: str) -> Path:
        staging = tmp_path / "staging" / "session-end"
        staging.mkdir(parents=True, exist_ok=True)
        dest = staging / f"{session_id}.jsonl"
        dest.write_text(
            "GARBAGE LINE\n"
            '{"type": "user", "content": "valid message"}\n',
            encoding="utf-8",
        )
        return dest

    def test_ingest_logs_warning_for_skipped_lines(self, tmp_path: Path) -> None:
        from ephemeris.ingest import ingest_one
        from ephemeris.log import IngestLogger
        from ephemeris.model import FakeModelClient

        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        log_path = tmp_path / "ephemeris.log"
        logger = IngestLogger(log_path)
        session_id = "m2-session-001"

        transcript_path = self._write_malformed_transcript(tmp_path, session_id)
        model = FakeModelClient(
            response=json.dumps({"operations": []})
        )

        result = ingest_one(
            transcript_path=transcript_path,
            wiki_root=wiki_root,
            model=model,
            log=logger,
            session_id=session_id,
            session_date="2026-04-15",
        )

        assert result.success
        entries = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))

        warning_entries = [
            e for e in entries
            if e.get("session_id") == session_id
            and e.get("phase") == "parse"
            and e.get("status") == "warning"
        ]
        assert len(warning_entries) == 1, (
            f"Expected 1 parse/warning entry, got {len(warning_entries)}: {warning_entries}"
        )
        assert "1" in warning_entries[0]["message"], (
            f"Warning message should mention skipped count: {warning_entries[0]['message']}"
        )

    def test_ingest_no_warning_for_clean_transcript(self, tmp_path: Path) -> None:
        from ephemeris.ingest import ingest_one
        from ephemeris.log import IngestLogger
        from ephemeris.model import FakeModelClient

        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        log_path = tmp_path / "ephemeris.log"
        logger = IngestLogger(log_path)
        session_id = "m2-session-002"

        transcript_path = self._copy_fixture("transcript_simple.jsonl", tmp_path, session_id)
        model = FakeModelClient(response=json.dumps({"operations": []}))

        ingest_one(
            transcript_path=transcript_path,
            wiki_root=wiki_root,
            model=model,
            log=logger,
            session_id=session_id,
            session_date="2026-04-15",
        )

        entries = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))

        warning_entries = [
            e for e in entries
            if e.get("session_id") == session_id
            and e.get("phase") == "parse"
            and e.get("status") == "warning"
        ]
        assert len(warning_entries) == 0
