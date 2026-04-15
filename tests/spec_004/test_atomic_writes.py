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
# AC-1.2: no partial page after merge-path write error
# ---------------------------------------------------------------------------

def test_no_partial_page_after_merge_path_write_error(tmp_path: Path, monkeypatch) -> None:
    """AC-1.2: After a fault on the 2nd page write in a multi-page run:
      (a) no .tmp files remain anywhere in wiki_root
      (b) the 2nd page does not exist with any (partial) content
      (c) the 1st page (pre-existing write target) was rolled back to pre-run state
    """
    import ephemeris.wiki as wiki_mod
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)

    # Pre-create both pages that the ingest will overwrite
    p1 = topics_dir / "topic-alpha.md"
    p2 = topics_dir / "topic-beta.md"
    p1.write_text("# Topic Alpha\n\nOriginal content.\n", encoding="utf-8")
    p2.write_text("# Topic Beta\n\nOriginal content.\n", encoding="utf-8")
    original_p1 = p1.read_bytes()
    original_p2 = p2.read_bytes()

    log_path = tmp_path / "ingest.log"
    transcript = _make_transcript(tmp_path, "sess-ac12", "talk about alpha and beta")

    call_count = {"n": 0}
    original_atomic = wiki_mod._atomic_write_text

    def fault_on_second(path, content):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("Injected fault on 2nd write")
        return original_atomic(path, content)

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", fault_on_second)

    from ephemeris.ingest import ingest_one

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=_fake_response_two_topics()),
        log=IngestLogger(log_path),
        session_id="sess-ac12",
        session_date="2026-04-15",
    )

    assert not result.success

    # (a) No .tmp files anywhere in wiki_root
    tmp_files = list(wiki_root.rglob("*.tmp"))
    assert tmp_files == [], f"Stale .tmp files found: {tmp_files}"

    # (b) page 2 rolled back to pre-run state (not partial new content)
    assert p2.read_bytes() == original_p2, (
        "Page 2 was not rolled back to pre-run content"
    )

    # (c) page 1 rolled back to pre-run state
    assert p1.read_bytes() == original_p1, (
        "Page 1 was not rolled back to pre-run content"
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
