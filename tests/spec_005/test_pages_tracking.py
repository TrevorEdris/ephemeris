"""tests/spec_005/test_pages_tracking.py — MAJOR-1 tests for pages_created/pages_updated tracking.

RED tests: these fail until PageResult gains pages_created/pages_updated fields
and ingest_one correctly classifies new vs existing pages.
"""
from __future__ import annotations

import json
import os
import sys
from io import StringIO
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Shared helpers (copied from test_cli_extension.py to keep tests self-contained)
# ---------------------------------------------------------------------------

def _make_transcript(staging_root: Path, session_id: str, content: str = "Hello world.") -> Path:
    """Write a minimal JSONL transcript to staging_root/session-end/<session_id>.jsonl."""
    staging_dir = staging_root / "session-end"
    staging_dir.mkdir(parents=True, exist_ok=True)
    t = staging_dir / f"{session_id}.jsonl"
    t.write_text(
        json.dumps({"type": "user", "content": content}) + "\n",
        encoding="utf-8",
    )
    return t


def _topic_op(name: str, overview: str = "An overview.") -> dict:
    return {
        "action": "create",
        "page_type": "topic",
        "page_name": name,
        "content": {"overview": overview, "details": ""},
        "cross_references": [],
    }


def _run_main(args: list[str], env: dict) -> tuple[int, str, str]:
    from ephemeris.ingest import main

    captured_out = StringIO()
    captured_err = StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = captured_out
    sys.stderr = captured_err
    old_env = {}
    try:
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
        try:
            main(args)
            code = 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return code, captured_out.getvalue(), captured_err.getvalue()


# ---------------------------------------------------------------------------
# Test: pages_created and pages_updated are first-class fields on PageResult
# ---------------------------------------------------------------------------

def test_page_result_has_pages_created_and_pages_updated_fields() -> None:
    """PageResult must have pages_created and pages_updated as first-class fields.

    RED: fails until PageResult gains these fields.
    """
    from ephemeris.ingest import PageResult
    from pathlib import Path

    result = PageResult(
        success=True,
        session_id="test-sess",
        pages_written=[Path("/wiki/topics/foo.md")],
        pages_created=[Path("/wiki/topics/foo.md")],
        pages_updated=[],
    )
    assert result.pages_created == [Path("/wiki/topics/foo.md")]
    assert result.pages_updated == []


# ---------------------------------------------------------------------------
# Test: pages_written == pages_created + pages_updated invariant
# ---------------------------------------------------------------------------

def test_pages_written_is_union_of_created_and_updated() -> None:
    """Invariant: len(pages_written) == len(pages_created) + len(pages_updated).

    RED: fails until PageResult has the new fields.
    """
    from ephemeris.ingest import PageResult
    from pathlib import Path

    p1 = Path("/wiki/topics/new.md")
    p2 = Path("/wiki/topics/existing.md")

    result = PageResult(
        success=True,
        session_id="test-sess",
        pages_written=[p1, p2],
        pages_created=[p1],
        pages_updated=[p2],
    )
    assert len(result.pages_written) == len(result.pages_created) + len(result.pages_updated)
    # Disjoint
    assert set(result.pages_created).isdisjoint(set(result.pages_updated))


# ---------------------------------------------------------------------------
# Test: pages_updated counted on merge path (ingest_one with pre-existing page)
# ---------------------------------------------------------------------------

def test_pages_updated_counted_on_merge_path(tmp_path: Path) -> None:
    """Pre-existing topic page → ingest_one reports pages_updated=1, pages_created=0.

    RED: fails until ingest_one correctly tracks pages_created vs pages_updated.
    """
    import json as _json
    from ephemeris.ingest import ingest_one
    from ephemeris.model import FakeModelClient, MergeResult
    from ephemeris.log import IngestLogger

    # Pre-create the topic page
    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    existing_page = topics_dir / "auth-service.md"
    existing_page.write_text(
        "# Auth Service\n\n## Overview\nUses JWT tokens.\n\n## Sessions\n> Source: [2026-04-14 old-sess]\n",
        encoding="utf-8",
    )

    # Transcript targeting the same topic
    staging_dir = tmp_path / "staging" / "session-end"
    staging_dir.mkdir(parents=True, exist_ok=True)
    transcript = staging_dir / "update-sess.jsonl"
    transcript.write_text(
        _json.dumps({"type": "user", "content": "Auth service update."}) + "\n",
        encoding="utf-8",
    )

    # FakeModelClient with a response that targets auth-service
    fake_response = _json.dumps({
        "operations": [{
            "action": "create",
            "page_type": "topic",
            "page_name": "auth-service",
            "content": {"overview": "Uses JWT tokens and OAuth.", "details": ""},
            "cross_references": [],
        }]
    })
    fake_merge = MergeResult(additions=["OAuth support added."], duplicates=[], conflicts=[])
    model = FakeModelClient(response=fake_response, merge_result=fake_merge)
    log_path = tmp_path / "test.log"
    logger = IngestLogger(log_path)

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id="update-sess",
        session_date="2026-04-15",
    )

    assert result.success, f"Expected success, got error: {result.error}"
    assert len(result.pages_updated) == 1, (
        f"Expected 1 updated page, got {len(result.pages_updated)}: {result.pages_updated}"
    )
    assert len(result.pages_created) == 0, (
        f"Expected 0 created pages, got {len(result.pages_created)}: {result.pages_created}"
    )
    assert len(result.pages_written) == 1


# ---------------------------------------------------------------------------
# Test: pages_created counted when no existing page
# ---------------------------------------------------------------------------

def test_pages_created_counted_on_new_page_path(tmp_path: Path) -> None:
    """No pre-existing topic page → ingest_one reports pages_created=1, pages_updated=0.

    RED: fails until ingest_one correctly tracks pages_created vs pages_updated.
    """
    import json as _json
    from ephemeris.ingest import ingest_one
    from ephemeris.model import FakeModelClient
    from ephemeris.log import IngestLogger

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir(parents=True)

    staging_dir = tmp_path / "staging" / "session-end"
    staging_dir.mkdir(parents=True, exist_ok=True)
    transcript = staging_dir / "new-sess.jsonl"
    transcript.write_text(
        _json.dumps({"type": "user", "content": "Brand new topic."}) + "\n",
        encoding="utf-8",
    )

    fake_response = _json.dumps({
        "operations": [{
            "action": "create",
            "page_type": "topic",
            "page_name": "brand-new-topic",
            "content": {"overview": "Something new.", "details": ""},
            "cross_references": [],
        }]
    })
    model = FakeModelClient(response=fake_response)
    log_path = tmp_path / "test.log"
    logger = IngestLogger(log_path)

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id="new-sess",
        session_date="2026-04-15",
    )

    assert result.success, f"Expected success, got error: {result.error}"
    assert len(result.pages_created) == 1, (
        f"Expected 1 created page, got {len(result.pages_created)}: {result.pages_created}"
    )
    assert len(result.pages_updated) == 0, (
        f"Expected 0 updated pages, got {len(result.pages_updated)}: {result.pages_updated}"
    )
    assert len(result.pages_written) == 1


# ---------------------------------------------------------------------------
# Test: CLI summary reports correct Pages created / Pages updated counts
# ---------------------------------------------------------------------------

def test_summary_reports_pages_updated_not_zero(tmp_path: Path) -> None:
    """CLI: pre-existing page → summary shows Pages updated: 1, Pages created: 0.

    RED: fails until main() uses pages_created/pages_updated from PageResult.
    """
    import json as _json
    from ephemeris import ingest as ingest_mod
    from ephemeris.ingest import PageResult
    from pathlib import Path as P

    # Pre-create wiki with an existing topic
    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    (topics_dir / "mytopic.md").write_text(
        "# Mytopic\n\n## Overview\nExisting content.\n\n## Sessions\n> Source: [2026-04-14 old]\n",
        encoding="utf-8",
    )

    staging_root = tmp_path / "staging"
    _make_transcript(staging_root, "upd-sess", "Updated info about mytopic.")

    # Patch ingest_one to return a PageResult reflecting an update
    original_ingest_one = ingest_mod.ingest_one
    updated_path = topics_dir / "mytopic.md"

    def patched_ingest_one(transcript_path, wiki_root, model, log, session_id, session_date, dry_run=False):
        result = original_ingest_one(transcript_path, wiki_root, model, log, session_id, session_date, dry_run)
        # Simulate the update tracking: force pages_updated to contain the path
        # (This test will pass GREEN once real ingest_one does this naturally)
        result.pages_created = []
        result.pages_updated = [updated_path]
        result.pages_written = [updated_path]
        return result

    ingest_mod.ingest_one = patched_ingest_one  # type: ignore[assignment]
    try:
        code, out, err = _run_main(
            [],
            {
                "EPHEMERIS_STAGING_ROOT": str(staging_root),
                "EPHEMERIS_WIKI_ROOT": str(wiki_root),
                "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
                "EPHEMERIS_MODEL_CLIENT": "fake",
            },
        )
    finally:
        ingest_mod.ingest_one = original_ingest_one  # type: ignore[assignment]

    assert code == 0, f"Expected exit 0, got {code}. stderr={err!r}"
    assert "Pages updated:      1" in out, f"Expected 'Pages updated: 1' in summary:\n{out!r}"
    assert "Pages created:      0" in out, f"Expected 'Pages created: 0' in summary:\n{out!r}"
