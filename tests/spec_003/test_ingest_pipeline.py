"""test_ingest_pipeline.py — Slice 2: Single-Transcript Extraction tests.

Tests AC-2.1 through AC-2.6 of SPEC-003.
All tests use FakeModelClient — Anthropic SDK is never imported.
Tests always copy fixtures to tmp_path so ingest_one may safely delete them.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _make_fake_response(operations: list[dict]) -> str:  # type: ignore[type-arg]
    """Return JSON string the FakeModelClient should emit."""
    return json.dumps({"operations": operations})


def _single_topic_op() -> dict:  # type: ignore[type-arg]
    return {
        "action": "create",
        "page_type": "topic",
        "page_name": "error-handling-strategy",
        "content": {
            "overview": "All errors use typed subclasses.",
            "details": "The team uses AppError as the base class.",
        },
        "cross_references": [],
    }


def _copy_fixture(name: str, tmp_path: Path, session_id: str) -> Path:
    """Copy a fixture JSONL to a tmp_path staging dir, return the staged path."""
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / f"{session_id}.jsonl"
    shutil.copy(FIXTURES / name, dest)
    return dest


def test_ingest_processes_staged_transcript(tmp_path: Path) -> None:
    """AC-2.2: ingest_one creates at least one wiki page from a staged transcript."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ephemeris.log"
    logger = IngestLogger(log_path)
    session_id = "test-session-001"
    transcript_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

    model = FakeModelClient(response=_make_fake_response([_single_topic_op()]))

    result = ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert result.success
    topic_file = wiki_root / "topics" / "error-handling-strategy.md"
    assert topic_file.exists(), f"Expected {topic_file} to be created"


def test_ingest_no_external_calls(tmp_path: Path) -> None:
    """AC-2.1: Ingestion uses FakeModelClient — anthropic module is NOT imported."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ephemeris.log"
    logger = IngestLogger(log_path)
    session_id = "test-session-002"
    transcript_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

    model = FakeModelClient(response=_make_fake_response([_single_topic_op()]))

    ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    # Anthropic SDK must not be imported during this test run
    assert "anthropic" not in sys.modules, (
        "anthropic SDK was imported during ingest_one — lazy import violated"
    )


def test_ingest_adds_citation_to_pages(tmp_path: Path) -> None:
    """AC-2.3: Each written page contains a citation with session date and ID."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ephemeris.log"
    logger = IngestLogger(log_path)
    session_id = "cite-session-003"
    session_date = "2026-04-15"
    transcript_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

    model = FakeModelClient(response=_make_fake_response([_single_topic_op()]))

    ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date=session_date,
    )

    topic_file = wiki_root / "topics" / "error-handling-strategy.md"
    content = topic_file.read_text(encoding="utf-8")
    expected_citation = f"> Source: [{session_date} {session_id}]"
    assert expected_citation in content, (
        f"Expected citation {expected_citation!r} in page content"
    )


def test_ingest_empty_transcript_no_pages(tmp_path: Path) -> None:
    """AC-2.4: Empty/greeting-only transcript produces no wiki pages."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ephemeris.log"
    logger = IngestLogger(log_path)
    session_id = "empty-session-004"
    transcript_path = _copy_fixture("transcript_empty.jsonl", tmp_path, session_id)

    # Model returns no operations for trivial transcript
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
    # No files should exist in wiki subdirectories
    topics_dir = wiki_root / "topics"
    entities_dir = wiki_root / "entities"
    decisions_file = wiki_root / "DECISIONS.md"
    assert not topics_dir.exists() or list(topics_dir.iterdir()) == []
    assert not entities_dir.exists() or list(entities_dir.iterdir()) == []
    assert not decisions_file.exists()


def test_ingest_malformed_response_no_partial_write(tmp_path: Path) -> None:
    """AC-2.5: Malformed model response causes failure with no partial writes."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ephemeris.log"
    logger = IngestLogger(log_path)
    session_id = "malformed-session-005"
    transcript_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

    # Return invalid JSON
    model = FakeModelClient(response="THIS IS NOT VALID JSON {{{{")

    result = ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert not result.success
    # No pages written
    assert not (wiki_root / "topics").exists() or list((wiki_root / "topics").iterdir()) == []


def test_ingest_consumes_transcript_on_success(tmp_path: Path) -> None:
    """AC-2.6: Staging file is deleted after successful ingestion."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log_path = tmp_path / "ephemeris.log"
    logger = IngestLogger(log_path)
    session_id = "consume-session-006"
    staged_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

    model = FakeModelClient(response=_make_fake_response([_single_topic_op()]))

    result = ingest_one(
        transcript_path=staged_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert result.success
    assert not staged_path.exists(), "Staged transcript must be deleted after success"
