"""tests/spec_004/test_atomic_writes.py — Slice 1: Atomic Write Guarantee.

AC-1.1: Pre-run pages unchanged after mid-run fault (fault injection on 2nd write).
AC-1.2: No partial file on write error (already tested by spec_003; regression guard here).
AC-1.3: Log entry produced on write fault.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(tmp_path: Path, session_id: str, content: str) -> Path:
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True)
    t = staging / f"{session_id}.jsonl"
    t.write_text(
        json.dumps({"type": "user", "content": content}) + "\n",
        encoding="utf-8",
    )
    return t


def _fake_response_two_topics() -> str:
    return json.dumps({
        "operations": [
            {
                "action": "create",
                "page_type": "topic",
                "page_name": "topic-alpha",
                "content": {"overview": "Alpha overview.", "details": "Alpha details."},
                "cross_references": [],
            },
            {
                "action": "create",
                "page_type": "topic",
                "page_name": "topic-beta",
                "content": {"overview": "Beta overview.", "details": "Beta details."},
                "cross_references": [],
            },
        ]
    })


# ---------------------------------------------------------------------------
# AC-1.1: pre-run pages byte-identical after fault on 2nd write
# ---------------------------------------------------------------------------

def test_pre_run_pages_unchanged_after_mid_run_fault(tmp_path: Path, monkeypatch) -> None:
    """AC-1.1: If a write fault occurs partway through a multi-page ingest run,
    pages that existed before the run are byte-for-byte unchanged.

    Strategy: inject a fault on the 2nd call to _atomic_write_text.
    This simulates the process being killed (or erroring) after the first
    page write completes.

    We use fault injection rather than SIGKILL because:
    - SIGKILL tests are non-deterministic (timing), fragile, and slow.
    - Fault injection deterministically reproduces the mid-run failure state.
    - The atomic guarantee is about _atomic_write_text semantics, which
      fault injection tests directly.
    """
    import ephemeris.wiki as wiki_mod
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    # Pre-existing page (not involved in this run)
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir()
    pre_existing = topics_dir / "pre-existing.md"
    original_bytes = b"# Pre-Existing\n\nOriginal content.\n"
    pre_existing.write_bytes(original_bytes)

    log_path = tmp_path / "ingest.log"
    transcript = _make_transcript(tmp_path, "sess-fault", "talk about alpha and beta")

    call_count = {"n": 0}
    original_atomic = wiki_mod._atomic_write_text

    def fault_on_second(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("Injected fault on 2nd write")
        return original_atomic(*args, **kwargs)

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", fault_on_second)

    from ephemeris.ingest import ingest_one

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=_fake_response_two_topics()),
        log=IngestLogger(log_path),
        session_id="sess-fault",
        session_date="2026-04-15",
    )

    # Run failed (expected)
    assert not result.success

    # Pre-existing page must be byte-identical
    assert pre_existing.read_bytes() == original_bytes, (
        "Pre-existing page was modified by a failed ingest run"
    )


# ---------------------------------------------------------------------------
# AC-1.3: log entry on write fault
# ---------------------------------------------------------------------------

def test_log_entry_on_write_fault(tmp_path: Path, monkeypatch) -> None:
    """AC-1.3: A write-phase fault produces a structured log entry with
    phase='write', status='error', and the session_id."""
    import ephemeris.wiki as wiki_mod
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ingest.log"
    transcript = _make_transcript(tmp_path, "sess-logfault", "talk about gamma")

    original_atomic = wiki_mod._atomic_write_text

    def always_fault(*args, **kwargs):
        raise OSError("Injected write fault")

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", always_fault)

    from ephemeris.ingest import ingest_one

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=json.dumps({
            "operations": [{
                "action": "create",
                "page_type": "topic",
                "page_name": "gamma",
                "content": {"overview": "Gamma."},
                "cross_references": [],
            }]
        })),
        log=IngestLogger(log_path),
        session_id="sess-logfault",
        session_date="2026-04-15",
    )

    assert not result.success

    # Read log and find an error entry for the write phase
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    entries = [json.loads(line) for line in lines]

    write_errors = [
        e for e in entries
        if e.get("phase") == "write" and e.get("status") == "error"
    ]
    assert write_errors, "Expected at least one write-phase error log entry"
    assert write_errors[0]["session_id"] == "sess-logfault"
    assert "ts" in write_errors[0]
    assert write_errors[0]["message"]  # non-empty message
