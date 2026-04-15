"""test_end_to_end.py — Slice 4: End-to-End Automation tests.

Tests AC-4.1 through AC-4.4 and CLI tests of SPEC-003.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent


def _copy_fixture(name: str, staging: Path, session_id: str) -> Path:
    """Copy a fixture JSONL to the staging dir."""
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / f"{session_id}.jsonl"
    shutil.copy(FIXTURES / name, dest)
    return dest


def _make_response(operations: list[dict]) -> str:  # type: ignore[type-arg]
    return json.dumps({"operations": operations})


def _topic_op(name: str = "error-handling-strategy") -> dict:  # type: ignore[type-arg]
    return {
        "action": "create",
        "page_type": "topic",
        "page_name": name,
        "content": {
            "overview": f"Overview for {name}.",
            "details": f"Details for {name}.",
        },
        "cross_references": [],
    }


def test_ingest_cli_processes_multiple_staged_transcripts(tmp_path: Path) -> None:
    """AC-4.3: ingest_all processes every staged transcript independently."""
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")

    # Stage three transcripts
    staging_dir = staging_root / "session-end"
    _copy_fixture("transcript_simple.jsonl", staging_dir, "session-a")
    _copy_fixture("transcript_simple.jsonl", staging_dir, "session-b")
    _copy_fixture("transcript_simple.jsonl", staging_dir, "session-c")

    model = FakeModelClient(response=_make_response([_topic_op("topic-a"),
                                                      _topic_op("topic-b")]))

    result = ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=model,
        log=logger,
    )

    assert result.success_count == 3
    assert result.failure_count == 0
    # All staged files deleted
    assert not list(staging_dir.glob("*.jsonl")), "All staged files must be consumed"


def test_ingest_cli_partial_failure_isolation(tmp_path: Path) -> None:
    """AC-4.4: One failed transcript doesn't prevent others from succeeding."""
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")

    staging_dir = staging_root / "session-end"
    _copy_fixture("transcript_simple.jsonl", staging_dir, "session-good")
    _copy_fixture("transcript_simple.jsonl", staging_dir, "session-bad")

    # Counter to alternate responses: fail on second call
    call_count = [0]

    def alternating_invoke(system_prompt: str, user_prompt: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: fail (return invalid JSON)
            return "INVALID JSON"
        else:
            # Second call: succeed
            return _make_response([_topic_op("good-topic")])

    model = FakeModelClient()
    model.invoke = alternating_invoke  # type: ignore[method-assign]

    result = ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=model,
        log=logger,
    )

    # One success, one failure
    assert result.success_count >= 1
    assert result.failure_count >= 1

    # Failed transcript must remain as .error file
    error_files = list(staging_dir.glob("*.error"))
    assert len(error_files) >= 1, "Failed transcript must have .error sibling"


def test_ingest_cli_idempotent_on_rerun(tmp_path: Path) -> None:
    """AC-4.3 idempotency: second run is a no-op (staging file consumed on first run)."""
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")

    staging_dir = staging_root / "session-end"
    _copy_fixture("transcript_simple.jsonl", staging_dir, "session-idem")

    model = FakeModelClient(response=_make_response([_topic_op()]))

    # First run
    result1 = ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=model,
        log=logger,
    )
    assert result1.success_count == 1

    # Count wiki pages after first run
    topics_before = list((wiki_root / "topics").iterdir()) if (wiki_root / "topics").exists() else []

    # Second run — staging is empty
    result2 = ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=model,
        log=logger,
    )
    assert result2.success_count == 0  # Nothing to process

    # Wiki pages unchanged
    topics_after = list((wiki_root / "topics").iterdir()) if (wiki_root / "topics").exists() else []
    assert len(topics_before) == len(topics_after), "Second run must not add duplicate pages"


def test_ingest_cli_dry_run_no_writes(tmp_path: Path) -> None:
    """--dry-run flag: parse + plan without writing any files."""
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")

    staging_dir = staging_root / "session-end"
    staged_path = _copy_fixture("transcript_simple.jsonl", staging_dir, "session-dry")

    model = FakeModelClient(response=_make_response([_topic_op()]))

    result = ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        dry_run=True,
    )

    assert result.success_count == 1
    # No pages written
    assert not (wiki_root / "topics").exists() or list((wiki_root / "topics").iterdir()) == []
    # Staging file NOT deleted in dry_run
    assert staged_path.exists(), "Dry-run must not delete staging file"
