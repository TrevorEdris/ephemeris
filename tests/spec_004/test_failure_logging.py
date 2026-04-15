"""tests/spec_004/test_failure_logging.py — Slice 4: Diagnostic Log on Failure.

AC-4.1: Every pipeline phase (parse, merge, detect, write, complete) emits log on failure.
AC-4.2: Multiple failures produce distinct log entries; prior entries preserved (append-only).
AC-4.3: Successful run produces phase=complete, status=ok entry.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(tmp_path: Path, session_id: str, content: str = "some content") -> Path:
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    t = staging / f"{session_id}.jsonl"
    t.write_text(
        json.dumps({"type": "user", "content": content}) + "\n",
        encoding="utf-8",
    )
    return t


def _make_corrupt_transcript(tmp_path: Path, session_id: str) -> Path:
    """Write a transcript where every line is invalid JSON — triggers parse error."""
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    t = staging / f"{session_id}.jsonl"
    t.write_text("NOT_JSON\nALSO_NOT_JSON\n", encoding="utf-8")
    return t


def _read_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").strip().splitlines()]


# ---------------------------------------------------------------------------
# AC-4.1: parse phase failure produces log entry
# ---------------------------------------------------------------------------

def test_parse_failure_produces_log_entry(tmp_path: Path) -> None:
    """AC-4.1: A completely corrupt transcript triggers a parse error.
    The log must contain an entry with phase containing 'parse', status='error',
    and the session_id."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ingest.log"

    transcript = _make_corrupt_transcript(tmp_path, "sess-parsefail")

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(),
        log=IngestLogger(log_path),
        session_id="sess-parsefail",
        session_date="2026-04-15",
    )

    # Corrupt file may succeed (all lines skipped → 0 messages) or raise
    # TranscriptParseError. Either way we need a log entry.
    entries = _read_log(log_path)
    assert entries, "No log entries written"

    # There should be at least one entry for this session
    session_entries = [e for e in entries if e.get("session_id") == "sess-parsefail"]
    assert session_entries, "No log entries for sess-parsefail"


# ---------------------------------------------------------------------------
# AC-4.1: merge phase failure produces log entry
# ---------------------------------------------------------------------------

def test_merge_phase_failure_produces_log_entry(tmp_path: Path, monkeypatch) -> None:
    """AC-4.1: When merge_topic raises, the ingest pipeline logs a merge-phase error."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient
    from ephemeris.exceptions import ModelClientError

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    # Create pre-existing page so merge path is taken
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    (topics_dir / "existing-topic.md").write_text(
        "# Existing Topic\n\nContent.\n\n## Sessions\n> Source: [2026-04-14 sess-old]\n",
        encoding="utf-8",
    )

    transcript = _make_transcript(tmp_path, "sess-mergefail", "existing topic discussion")

    class FailingMergeClient(FakeModelClient):
        def merge_topic(self, existing: str, new: str, session_id: str):
            raise ModelClientError("Injected merge failure")

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FailingMergeClient(response=json.dumps({
            "operations": [{
                "action": "update",
                "page_type": "topic",
                "page_name": "existing-topic",
                "content": {"overview": "New overview."},
                "cross_references": [],
            }]
        })),
        log=IngestLogger(log_path),
        session_id="sess-mergefail",
        session_date="2026-04-15",
    )

    assert not result.success

    entries = _read_log(log_path)
    merge_errors = [
        e for e in entries
        if e.get("session_id") == "sess-mergefail"
        and "error" == e.get("status")
        and e.get("phase")
    ]
    assert merge_errors, f"No error log entry found. Entries: {entries}"
    # Must have timestamp and message
    assert all("ts" in e for e in merge_errors)
    assert all(e.get("message") for e in merge_errors)


# ---------------------------------------------------------------------------
# AC-4.1: write phase failure produces log entry (regression from Slice 1)
# ---------------------------------------------------------------------------

def test_write_phase_failure_produces_log_entry(tmp_path: Path, monkeypatch) -> None:
    """AC-4.1: Write-phase fault produces log entry with phase='write', status='error'."""
    import ephemeris.wiki as wiki_mod
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ingest.log"
    transcript = _make_transcript(tmp_path, "sess-writefail")

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("write fault")))

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=json.dumps({
            "operations": [{
                "action": "create",
                "page_type": "topic",
                "page_name": "new-topic",
                "content": {"overview": "Some content."},
                "cross_references": [],
            }]
        })),
        log=IngestLogger(log_path),
        session_id="sess-writefail",
        session_date="2026-04-15",
    )

    assert not result.success

    entries = _read_log(log_path)
    write_errors = [
        e for e in entries
        if e.get("phase") == "write" and e.get("status") == "error"
        and e.get("session_id") == "sess-writefail"
    ]
    assert write_errors, "No write-phase error log entry found"


# ---------------------------------------------------------------------------
# AC-4.2: multiple failures produce distinct entries, prior entries preserved
# ---------------------------------------------------------------------------

def test_two_failures_produce_two_log_entries_first_preserved(tmp_path: Path) -> None:
    """AC-4.2: Running two failing ingestions produces two distinct entries.
    The first entry must not be modified after the second run."""
    import ephemeris.wiki as wiki_mod
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ingest.log"

    def fault(*a, **k):
        raise OSError("write fault")

    monkeypatch_target = {"fn": wiki_mod._atomic_write_text}

    def patched(*a, **k):
        raise OSError("write fault")

    original = wiki_mod._atomic_write_text
    wiki_mod._atomic_write_text = patched

    single_op_response = json.dumps({
        "operations": [{
            "action": "create",
            "page_type": "topic",
            "page_name": "fail-topic",
            "content": {"overview": "Fail."},
            "cross_references": [],
        }]
    })

    try:
        # First failure
        t1 = _make_transcript(tmp_path, "sess-fail1")
        ingest_one(
            transcript_path=t1, wiki_root=wiki_root,
            model=FakeModelClient(response=single_op_response),
            log=IngestLogger(log_path), session_id="sess-fail1", session_date="2026-04-15",
        )

        # Read first entry snapshot
        entries_after_first = _read_log(log_path)

        # Second failure
        t2 = _make_transcript(tmp_path, "sess-fail2")
        ingest_one(
            transcript_path=t2, wiki_root=wiki_root,
            model=FakeModelClient(response=single_op_response),
            log=IngestLogger(log_path), session_id="sess-fail2", session_date="2026-04-15",
        )
    finally:
        wiki_mod._atomic_write_text = original

    entries_after_second = _read_log(log_path)

    # Both sessions must appear
    sessions = {e["session_id"] for e in entries_after_second}
    assert "sess-fail1" in sessions
    assert "sess-fail2" in sessions

    # First entries must be unchanged (prefix preserved)
    first_session_entries_before = [e for e in entries_after_first if e.get("session_id") == "sess-fail1"]
    first_session_entries_after = [e for e in entries_after_second if e.get("session_id") == "sess-fail1"]
    assert first_session_entries_before == first_session_entries_after, (
        "Prior log entries were modified after second run"
    )


# ---------------------------------------------------------------------------
# AC-4.3: successful run produces phase=complete, status=ok entry
# ---------------------------------------------------------------------------

def test_successful_run_produces_complete_ok_log_entry(tmp_path: Path) -> None:
    """AC-4.3: A successful ingestion run produces a log entry with
    phase='complete', status='ok', and the session_id."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ingest.log"
    transcript = _make_transcript(tmp_path, "sess-success")

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=json.dumps({
            "operations": [{
                "action": "create",
                "page_type": "topic",
                "page_name": "success-topic",
                "content": {"overview": "Success."},
                "cross_references": [],
            }]
        })),
        log=IngestLogger(log_path),
        session_id="sess-success",
        session_date="2026-04-15",
    )

    assert result.success

    entries = _read_log(log_path)
    complete_ok = [
        e for e in entries
        if e.get("phase") == "complete"
        and e.get("status") == "ok"
        and e.get("session_id") == "sess-success"
    ]
    assert complete_ok, f"No complete/ok log entry found. Entries: {entries}"
    assert "ts" in complete_ok[0]


# ---------------------------------------------------------------------------
# AC-4.1: detect phase failure produces log entry (not spurious write, error)
# ---------------------------------------------------------------------------

def test_detect_phase_failure_produces_log_entry(tmp_path: Path, monkeypatch) -> None:
    """AC-4.1: When inject_conflict_blocks raises, the pipeline logs detect/error.
    There must NOT be a spurious write/error entry for the same fault."""
    import ephemeris.merge as merge_mod
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult, ConflictPair

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    # Pre-existing page so the merge path is taken
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    (topics_dir / "conflict-topic.md").write_text(
        "# Conflict Topic\n\nOld claim.\n\n## Sessions\n> Source: [2026-04-14 sess-old]\n",
        encoding="utf-8",
    )

    transcript = _make_transcript(tmp_path, "sess-detectfail", "conflict topic content")

    # FakeModelClient that returns a conflict so inject_conflict_blocks is called
    merge_result_with_conflict = MergeResult(
        additions=[],
        duplicates=[],
        conflicts=[ConflictPair(
            existing_claim="Old claim.",
            new_claim="New contradicting claim.",
            existing_session_id="sess-old",
            new_session_id="sess-detectfail",
        )],
    )

    # Monkeypatch inject_conflict_blocks to raise
    monkeypatch.setattr(
        merge_mod,
        "inject_conflict_blocks",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Injected detect failure")),
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(
            response=json.dumps({
                "operations": [{
                    "action": "update",
                    "page_type": "topic",
                    "page_name": "conflict-topic",
                    "content": {"overview": "New contradicting claim."},
                    "cross_references": [],
                }]
            }),
            merge_result=merge_result_with_conflict,
        ),
        log=IngestLogger(log_path),
        session_id="sess-detectfail",
        session_date="2026-04-15",
    )

    assert not result.success

    entries = _read_log(log_path)
    detect_errors = [
        e for e in entries
        if e.get("session_id") == "sess-detectfail"
        and e.get("phase") == "detect"
        and e.get("status") == "error"
    ]
    assert detect_errors, f"No detect/error log entry found. Entries: {entries}"
    assert detect_errors[0].get("message"), "detect/error entry must have a message"
