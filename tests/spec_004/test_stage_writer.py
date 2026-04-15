"""tests/spec_004/test_stage_writer.py — Transactional wiki write tests.

Tests for StageWriter: commit, rollback, crash recovery via orphan journals,
and integration with ingest_one.

RED phase: all tests will fail until stage.py is implemented.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(tmp_path: Path, session_id: str, content: str = "talk about alpha") -> Path:
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    t = staging / f"{session_id}.jsonl"
    t.write_text(
        json.dumps({"type": "user", "content": content}) + "\n",
        encoding="utf-8",
    )
    return t


def _fake_two_topics_response() -> str:
    return json.dumps({
        "operations": [
            {
                "action": "create",
                "page_type": "topic",
                "page_name": "alpha",
                "content": {"overview": "Alpha overview.", "details": "Alpha details."},
                "cross_references": [],
            },
            {
                "action": "create",
                "page_type": "topic",
                "page_name": "beta",
                "content": {"overview": "Beta overview.", "details": "Beta details."},
                "cross_references": [],
            },
        ]
    })


def _make_logger(tmp_path: Path):
    from ephemeris.log import IngestLogger
    return IngestLogger(tmp_path / "ingest.log")


# ---------------------------------------------------------------------------
# 1. commit: all writes land, journal deleted
# ---------------------------------------------------------------------------

def test_stage_writer_commits_all_writes_on_success(tmp_path: Path) -> None:
    """All staged writes land with correct content; journal file is deleted on success."""
    from ephemeris.stage import StageWriter
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "log")

    p1 = wiki_root / "topics" / "page-one.md"
    p2 = wiki_root / "topics" / "page-two.md"
    p3 = wiki_root / "topics" / "page-three.md"

    with StageWriter(wiki_root, logger) as stage:
        stage.stage_write(p1, "content one")
        stage.stage_write(p2, "content two")
        stage.stage_write(p3, "content three")

    assert p1.read_text(encoding="utf-8") == "content one"
    assert p2.read_text(encoding="utf-8") == "content two"
    assert p3.read_text(encoding="utf-8") == "content three"

    # No journal file left behind
    journals = list(wiki_root.glob(".ephemeris-journal-*.json"))
    assert journals == [], f"Journal file(s) not cleaned up: {journals}"


# ---------------------------------------------------------------------------
# 2. rollback: pre-existing page P1 restored, new P2 absent
# ---------------------------------------------------------------------------

def test_stage_writer_rolls_back_pre_existing_page_on_failure(tmp_path: Path, monkeypatch) -> None:
    """If a fault occurs mid-apply, P1 (pre-existing, already replaced) is rolled back
    to its original content; P2 (not yet applied) does not exist."""
    from ephemeris.stage import StageWriter
    import ephemeris.wiki as wiki_mod
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)

    p1 = topics_dir / "page-one.md"
    p1.write_text("OLD CONTENT", encoding="utf-8")
    p2 = topics_dir / "page-two.md"

    # Fault on 2nd call to _atomic_write_text (p2's write)
    call_count = {"n": 0}
    original_atomic = wiki_mod._atomic_write_text

    def fault_on_second(path, content):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("Injected fault on 2nd write")
        return original_atomic(path, content)

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", fault_on_second)

    logger = IngestLogger(tmp_path / "log")

    with pytest.raises(OSError):
        with StageWriter(wiki_root, logger) as stage:
            stage.stage_write(p1, "NEW CONTENT")
            stage.stage_write(p2, "NEW CONTENT")
        # The commit happens on __exit__; exception propagates

    # P1 must be rolled back to original
    assert p1.read_text(encoding="utf-8") == "OLD CONTENT", (
        f"P1 was not rolled back: {p1.read_text()!r}"
    )
    # P2 must not exist (was never applied)
    assert not p2.exists(), "P2 should not exist after rollback"

    # Journal cleaned up
    journals = list(wiki_root.glob(".ephemeris-journal-*.json"))
    assert journals == [], f"Journal not cleaned up after rollback: {journals}"


# ---------------------------------------------------------------------------
# 3. rollback: newly-created page deleted on rollback
# ---------------------------------------------------------------------------

def test_stage_writer_deletes_newly_created_page_on_rollback(tmp_path: Path, monkeypatch) -> None:
    """A page that did not exist pre-run is deleted if the run fails after it was created."""
    from ephemeris.stage import StageWriter
    import ephemeris.wiki as wiki_mod
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)

    p1 = topics_dir / "new-page.md"
    p2 = topics_dir / "second-page.md"
    assert not p1.exists()

    call_count = {"n": 0}
    original_atomic = wiki_mod._atomic_write_text

    def fault_on_second(path, content):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("Injected fault on 2nd write")
        return original_atomic(path, content)

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", fault_on_second)

    logger = IngestLogger(tmp_path / "log")

    with pytest.raises(OSError):
        with StageWriter(wiki_root, logger) as stage:
            stage.stage_write(p1, "NEW PAGE CONTENT")
            stage.stage_write(p2, "SECOND PAGE CONTENT")

    # P1 was newly created then applied; must be deleted on rollback
    assert not p1.exists(), "Newly created page should be deleted on rollback"
    assert not p2.exists()


# ---------------------------------------------------------------------------
# 4. journal written before any atomic replace
# ---------------------------------------------------------------------------

def test_stage_writer_journal_written_before_any_atomic_replace(tmp_path: Path) -> None:
    """The journal file must be written to disk before any os.replace for page files."""
    from ephemeris.stage import StageWriter
    import ephemeris.wiki as wiki_mod
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "log")

    p1 = wiki_root / "topics" / "page.md"
    call_order: list[str] = []

    original_atomic = wiki_mod._atomic_write_text

    def recording_atomic(path, content):
        # Record whether journal exists at the time of this page write
        journals = list(wiki_root.glob(".ephemeris-journal-*.json"))
        call_order.append(("journal_present", bool(journals), str(path)))
        return original_atomic(path, content)

    import ephemeris.wiki as wiki_mod2
    old_atomic = wiki_mod2._atomic_write_text
    wiki_mod2._atomic_write_text = recording_atomic

    try:
        with StageWriter(wiki_root, logger) as stage:
            stage.stage_write(p1, "content")
    finally:
        wiki_mod2._atomic_write_text = old_atomic

    # The page write should have happened with the journal already present
    page_calls = [c for c in call_order if "topics" in c[2]]
    assert page_calls, "No page write recorded"
    assert page_calls[0][1] is True, (
        "Journal was NOT present when page write occurred"
    )


# ---------------------------------------------------------------------------
# 5. recover_orphans: restores pre-run state from leftover journal
# ---------------------------------------------------------------------------

def test_recover_orphans_restores_pre_run_state_from_leftover_journal(tmp_path: Path) -> None:
    """recover_orphans reads a leftover journal and restores pre-run content."""
    from ephemeris.stage import StageWriter
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    log_path = tmp_path / "log"

    # Simulate a crashed run: page has NEW content but journal records OLD content
    p1 = topics_dir / "crashed-page.md"
    p1.write_text("NEW CONTENT (post-crash)", encoding="utf-8")

    journal = {
        "run_id": "testabc123",
        "wiki_root": str(wiki_root),
        "entries": [
            {
                "path": str(p1),
                "old_content": "OLD CONTENT (pre-run)",
            }
        ],
    }
    journal_path = wiki_root / ".ephemeris-journal-testabc123.json"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    logger = IngestLogger(log_path)
    recovered = StageWriter.recover_orphans(wiki_root, logger)

    assert recovered == 1
    assert not journal_path.exists(), "Journal should be deleted after recovery"
    assert p1.read_text(encoding="utf-8") == "OLD CONTENT (pre-run)", (
        f"Page not restored: {p1.read_text()!r}"
    )

    # Check a log entry was written
    log_entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
    recovery_entries = [e for e in log_entries if e.get("phase") == "recover"]
    assert recovery_entries, "No recovery log entry written"
    assert recovery_entries[0]["status"] == "ok"


# ---------------------------------------------------------------------------
# 6. recover_orphans: deletes newly-created pages from prior run
# ---------------------------------------------------------------------------

def test_recover_orphans_deletes_newly_created_pages_from_prior_run(tmp_path: Path) -> None:
    """recover_orphans deletes pages whose old_content is None (new pages from a crashed run)."""
    from ephemeris.stage import StageWriter
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)

    p_new = topics_dir / "new-from-crashed-run.md"
    p_new.write_text("content written during crashed run", encoding="utf-8")

    journal = {
        "run_id": "newpage456",
        "wiki_root": str(wiki_root),
        "entries": [
            {
                "path": str(p_new),
                "old_content": None,
            }
        ],
    }
    journal_path = wiki_root / ".ephemeris-journal-newpage456.json"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    recovered = StageWriter.recover_orphans(wiki_root, IngestLogger(tmp_path / "log"))

    assert recovered == 1
    assert not p_new.exists(), "Newly-created page should be deleted by recover_orphans"
    assert not journal_path.exists()


# ---------------------------------------------------------------------------
# 7. recover_orphans: noop when no journals
# ---------------------------------------------------------------------------

def test_recover_orphans_noop_when_no_journals_present(tmp_path: Path) -> None:
    """recover_orphans returns 0 and does nothing when no journal files exist."""
    from ephemeris.stage import StageWriter
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    result = StageWriter.recover_orphans(wiki_root, IngestLogger(tmp_path / "log"))
    assert result == 0


# ---------------------------------------------------------------------------
# 8. ingest_one: recover_orphans called before processing
# ---------------------------------------------------------------------------

def test_ingest_one_calls_recover_orphans_before_processing(tmp_path: Path) -> None:
    """Integration: an orphan journal is recovered before the new ingest run begins."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    log_path = tmp_path / "log"

    # Plant an orphan journal: page has new content, journal says old
    orphan_page = topics_dir / "orphan-page.md"
    orphan_page.write_text("ORPHAN NEW CONTENT", encoding="utf-8")

    journal = {
        "run_id": "orphanabc",
        "wiki_root": str(wiki_root),
        "entries": [
            {
                "path": str(orphan_page),
                "old_content": "ORPHAN OLD CONTENT",
            }
        ],
    }
    journal_path = wiki_root / ".ephemeris-journal-orphanabc.json"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    transcript = _make_transcript(tmp_path, "sess-orphan-test")

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response='{"operations": []}'),
        log=IngestLogger(log_path),
        session_id="sess-orphan-test",
        session_date="2026-04-15",
    )

    # Recovery must have happened: journal gone, page restored
    assert not journal_path.exists(), "Orphan journal should have been recovered"
    assert orphan_page.read_text(encoding="utf-8") == "ORPHAN OLD CONTENT", (
        "Orphan page not restored before new ingest run"
    )


# ---------------------------------------------------------------------------
# 9. ingest_one: rollback restores pages on write-phase failure
# ---------------------------------------------------------------------------

def test_ingest_one_rollback_restores_pages_on_write_phase_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """End-to-end: pre-existing pages are restored when the write phase fails mid-run."""
    import ephemeris.wiki as wiki_mod
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    log_path = tmp_path / "log"

    # Pre-create both pages that the ingest will write
    p_alpha = topics_dir / "alpha.md"
    p_beta = topics_dir / "beta.md"
    p_alpha.write_text("OLD ALPHA", encoding="utf-8")
    p_beta.write_text("OLD BETA", encoding="utf-8")

    transcript = _make_transcript(tmp_path, "sess-rollback-e2e", "alpha and beta topics")

    call_count = {"n": 0}
    original_atomic = wiki_mod._atomic_write_text

    def fault_on_second(path, content):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("Injected fault on 2nd write")
        return original_atomic(path, content)

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", fault_on_second)

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=_fake_two_topics_response()),
        log=IngestLogger(log_path),
        session_id="sess-rollback-e2e",
        session_date="2026-04-15",
    )

    assert not result.success

    # Both pages must be restored to pre-run state
    assert p_alpha.read_text(encoding="utf-8") == "OLD ALPHA", (
        f"alpha not rolled back: {p_alpha.read_text()!r}"
    )
    assert p_beta.read_text(encoding="utf-8") == "OLD BETA", (
        f"beta not rolled back: {p_beta.read_text()!r}"
    )


# ---------------------------------------------------------------------------
# 10. Rewritten Slice 1 AC-1.1 test: write-target page rolled back
# ---------------------------------------------------------------------------

def test_pre_run_pages_unchanged_after_mid_run_fault_write_targets(
    tmp_path: Path, monkeypatch
) -> None:
    """AC-1.1 (strengthened): topics/alpha.md is a WRITE TARGET (not a bystander).
    After a fault on the 2nd write, topics/alpha.md must contain its pre-run content
    and topics/beta.md must not exist.
    """
    import ephemeris.wiki as wiki_mod
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    log_path = tmp_path / "log"

    # Pre-create alpha (write target — will be merged/overwritten by ingest)
    p_alpha = topics_dir / "alpha.md"
    p_alpha.write_text("OLD ALPHA", encoding="utf-8")
    # beta does not exist pre-run
    p_beta = topics_dir / "beta.md"

    transcript = _make_transcript(tmp_path, "sess-ac11-strengthened", "alpha and beta")

    call_count = {"n": 0}
    original_atomic = wiki_mod._atomic_write_text

    def fault_on_second(path, content):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("Injected fault on 2nd write")
        return original_atomic(path, content)

    monkeypatch.setattr(wiki_mod, "_atomic_write_text", fault_on_second)

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=FakeModelClient(response=_fake_two_topics_response()),
        log=IngestLogger(log_path),
        session_id="sess-ac11-strengthened",
        session_date="2026-04-15",
    )

    assert not result.success

    # alpha (pre-existing write target) must be rolled back to "OLD ALPHA"
    assert p_alpha.read_text(encoding="utf-8") == "OLD ALPHA", (
        f"alpha was not rolled back: {p_alpha.read_text()!r}"
    )
    # beta must not exist (was never committed; any partial must be cleaned up)
    assert not p_beta.exists(), "beta should not exist after rollback"
