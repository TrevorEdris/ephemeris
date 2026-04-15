"""test_page_routing.py — Slice 3: Page Type Routing tests.

Tests AC-3.1 through AC-3.5 of SPEC-003.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _make_response(operations: list[dict]) -> str:  # type: ignore[type-arg]
    return json.dumps({"operations": operations})


def _copy_fixture(name: str, tmp_path: Path, session_id: str) -> Path:
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / f"{session_id}.jsonl"
    shutil.copy(FIXTURES / name, dest)
    return dest


def test_decision_goes_to_decisions_log(tmp_path: Path) -> None:
    """AC-3.1: Decision operations are written to wiki/DECISIONS.md."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")
    session_id = "decision-session-001"
    transcript_path = _copy_fixture("transcript_decision.jsonl", tmp_path, session_id)

    decision_op = {
        "action": "create",
        "page_type": "decision",
        "page_name": "Use forward-only database migrations",
        "content": {
            "decision": "Use forward-only migrations with explicit rollback scripts.",
            "rationale": "Auto-rollback can leave the database in an inconsistent state.",
            "date": "2026-04-15",
        },
        "cross_references": [],
    }
    model = FakeModelClient(response=_make_response([decision_op]))

    result = ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert result.success
    decisions_file = wiki_root / "DECISIONS.md"
    assert decisions_file.exists(), "DECISIONS.md must be created"
    content = decisions_file.read_text(encoding="utf-8")
    assert "Use forward-only" in content, "Decision title must appear"
    assert "Auto-rollback" in content, "Rationale must appear"
    assert f"> Source: [2026-04-15 {session_id}]" in content, "Citation must appear"


def test_entity_page_created_with_role_section(tmp_path: Path) -> None:
    """AC-3.2: Entity operations create an entity page with ## Role section."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")
    session_id = "entity-session-002"
    transcript_path = _copy_fixture("transcript_entity.jsonl", tmp_path, session_id)

    entity_op = {
        "action": "create",
        "page_type": "entity",
        "page_name": "IngestEngine",
        "content": {
            "role": "Processes staged transcripts through the Claude model to extract structured knowledge.",
            "relationships": [
                {"entity": "ModelClient", "description": "invokes for model calls"},
                {"entity": "WikiWriter", "description": "delegates page writes"},
            ],
        },
        "cross_references": [],
    }
    model = FakeModelClient(response=_make_response([entity_op]))

    result = ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert result.success
    entity_file = wiki_root / "entities" / "IngestEngine.md"
    assert entity_file.exists(), "entities/IngestEngine.md must be created"
    content = entity_file.read_text(encoding="utf-8")
    assert "## Role" in content, "Entity page must have ## Role section"
    assert "Processes staged transcripts" in content


def test_topic_page_created_with_overview(tmp_path: Path) -> None:
    """AC-3.3: Topic operations create a topic page with ## Overview section."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")
    session_id = "topic-session-003"
    transcript_path = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id)

    topic_op = {
        "action": "create",
        "page_type": "topic",
        "page_name": "atomic-write-pattern",
        "content": {
            "overview": "All file writes use temp + atomic rename for crash safety.",
            "details": "Write to .tmp file in same directory, then os.replace().",
        },
        "cross_references": [],
    }
    model = FakeModelClient(response=_make_response([topic_op]))

    result = ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert result.success
    topic_file = wiki_root / "topics" / "atomic-write-pattern.md"
    assert topic_file.exists(), "topics/atomic-write-pattern.md must be created"
    content = topic_file.read_text(encoding="utf-8")
    assert "## Overview" in content, "Topic page must have ## Overview section"
    assert "All file writes" in content


def test_existing_page_content_preserved_on_update(tmp_path: Path) -> None:
    """AC-3.4: Update action preserves prior page content (append-only merge)."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")

    # First ingestion — creates the page
    session_id_1 = "topic-session-004a"
    transcript_path_1 = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id_1)
    create_op = {
        "action": "create",
        "page_type": "topic",
        "page_name": "error-handling-strategy",
        "content": {
            "overview": "Original overview from session 1.",
            "details": "Original details from session 1.",
        },
        "cross_references": [],
    }
    ingest_one(
        transcript_path=transcript_path_1,
        wiki_root=wiki_root,
        model=FakeModelClient(response=_make_response([create_op])),
        log=logger,
        session_id=session_id_1,
        session_date="2026-04-15",
    )

    # Verify original content
    topic_file = wiki_root / "topics" / "error-handling-strategy.md"
    original_content = topic_file.read_text(encoding="utf-8")
    assert "Original overview from session 1." in original_content

    # Second ingestion — updates the page
    session_id_2 = "topic-session-004b"
    transcript_path_2 = _copy_fixture("transcript_simple.jsonl", tmp_path, session_id_2)
    update_op = {
        "action": "update",
        "page_type": "topic",
        "page_name": "error-handling-strategy",
        "content": {
            "overview": "Updated overview from session 2.",
            "details": "New detail from session 2.",
        },
        "cross_references": [],
    }
    ingest_one(
        transcript_path=transcript_path_2,
        wiki_root=wiki_root,
        model=FakeModelClient(response=_make_response([update_op])),
        log=logger,
        session_id=session_id_2,
        session_date="2026-04-15",
    )

    updated_content = topic_file.read_text(encoding="utf-8")
    # Original content must be preserved
    assert "Original overview from session 1." in updated_content, (
        "Original content must be preserved after update"
    )
    # Citation from both sessions must appear
    assert session_id_1 in updated_content
    assert session_id_2 in updated_content


def test_cross_references_linked_bidirectionally(tmp_path: Path) -> None:
    """AC-3.5: Cross-referenced pages link to each other."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    logger = IngestLogger(tmp_path / "ephemeris.log")
    session_id = "xref-session-005"
    transcript_path = _copy_fixture("transcript_entity.jsonl", tmp_path, session_id)

    # Two entity pages that reference each other
    ops = [
        {
            "action": "create",
            "page_type": "entity",
            "page_name": "IngestEngine",
            "content": {
                "role": "Processes transcripts.",
                "relationships": [{"entity": "ModelClient", "description": "invokes"}],
            },
            "cross_references": ["ModelClient"],
        },
        {
            "action": "create",
            "page_type": "entity",
            "page_name": "ModelClient",
            "content": {
                "role": "Abstracts model invocation.",
                "relationships": [],
            },
            "cross_references": ["IngestEngine"],
        },
    ]
    model = FakeModelClient(response=_make_response(ops))

    result = ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=model,
        log=logger,
        session_id=session_id,
        session_date="2026-04-15",
    )

    assert result.success
    ingest_content = (wiki_root / "entities" / "IngestEngine.md").read_text(encoding="utf-8")
    model_content = (wiki_root / "entities" / "ModelClient.md").read_text(encoding="utf-8")

    # Each page should link to the other
    assert "ModelClient" in ingest_content, "IngestEngine page must reference ModelClient"
    assert "IngestEngine" in model_content, "ModelClient page must reference IngestEngine"
