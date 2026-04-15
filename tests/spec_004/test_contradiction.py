"""tests/spec_004/test_contradiction.py — Slice 3: Contradiction Detection.

AC-3.1: Conflict block injected adjacent to contradicted claim.
AC-3.2: Conflict block begins with exactly '> ⚠️ Conflict:'.
AC-3.3: No conflict block added when no contradiction.
AC-3.4: Affirming session resolves conflict block.
Pure fn: render_conflict_block unit test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(tmp_path: Path, session_id: str, content: str) -> Path:
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True, exist_ok=True)
    t = staging / f"{session_id}.jsonl"
    t.write_text(
        json.dumps({"type": "user", "content": content}) + "\n",
        encoding="utf-8",
    )
    return t


def _existing_topic_page(wiki_root: Path, name: str, content: str) -> Path:
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    page = topics_dir / f"{name}.md"
    page.write_text(content, encoding="utf-8")
    return page


def _topic_op(name: str, overview: str) -> dict:
    return {
        "action": "update",
        "page_type": "topic",
        "page_name": name,
        "content": {"overview": overview},
        "cross_references": [],
    }


# ---------------------------------------------------------------------------
# Pure function unit test — render_conflict_block
# ---------------------------------------------------------------------------

def test_render_conflict_block_pure_function() -> None:
    """render_conflict_block must return the exact format string from AC-3.2
    without any filesystem or model involvement."""
    from ephemeris.merge import render_conflict_block
    from ephemeris.model import ConflictPair

    pair = ConflictPair(
        existing_claim="X uses port 8080",
        new_claim="X uses port 9090",
        existing_session_id="sess-a",
        new_session_id="sess-b",
    )
    block = render_conflict_block(pair)
    assert block.startswith("> ⚠️ Conflict:")
    assert "sess-b" in block
    assert "X uses port 9090" in block
    assert "sess-a" in block


# ---------------------------------------------------------------------------
# AC-3.2: Exact conflict block format
# ---------------------------------------------------------------------------

def test_conflict_block_uses_exact_format() -> None:
    """AC-3.2: The conflict block must begin with '> ⚠️ Conflict:' followed
    by a description naming both the new-session and prior-session IDs."""
    from ephemeris.merge import render_conflict_block
    from ephemeris.model import ConflictPair

    pair = ConflictPair(
        existing_claim="Service A is stateless",
        new_claim="Service A maintains local state",
        existing_session_id="sess-prior",
        new_session_id="sess-new",
    )
    block = render_conflict_block(pair)

    # Exact prefix check
    assert block.startswith("> ⚠️ Conflict:"), f"Block does not start with marker: {block!r}"
    # Session IDs referenced
    assert "sess-new" in block
    assert "sess-prior" in block
    # Claims referenced
    assert "Service A maintains local state" in block


# ---------------------------------------------------------------------------
# AC-3.1: Conflict block injected adjacent to contradicted claim
# ---------------------------------------------------------------------------

def test_contradiction_injects_conflict_block_adjacent_to_claim(tmp_path: Path) -> None:
    """AC-3.1: When new session asserts a contradicting claim, the merged page
    contains a conflict block immediately following the contradicted claim."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import ConflictPair, FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    existing_claim = "X uses port 8080"
    new_claim = "X uses port 9090"
    original_content = (
        f"# Service X\n\n## Overview\n{existing_claim}\n\n"
        "## Sessions\n> Source: [2026-04-14 sess-a]\n"
    )
    page = _existing_topic_page(wiki_root, "service-x", original_content)

    conflict = ConflictPair(
        existing_claim=existing_claim,
        new_claim=new_claim,
        existing_session_id="sess-a",
        new_session_id="sess-b",
    )
    scripted_merge = MergeResult(additions=[], duplicates=[], conflicts=[conflict])
    transcript = _make_transcript(tmp_path, "sess-b", "service x uses port 9090")
    model = FakeModelClient(
        response=json.dumps({"operations": [_topic_op("service-x", new_claim)]}),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-b",
        session_date="2026-04-15",
    )
    assert result.success

    page_text = page.read_text(encoding="utf-8")
    assert "> ⚠️ Conflict:" in page_text, f"No conflict block in page:\n{page_text}"

    # Block must appear adjacent (immediately after) the existing claim line
    lines = page_text.splitlines()
    claim_idx = next(
        (i for i, line in enumerate(lines) if existing_claim in line), None
    )
    assert claim_idx is not None, "Existing claim not found in page"
    # The conflict block must be on one of the lines immediately following
    adjacent_lines = lines[claim_idx + 1: claim_idx + 3]
    assert any("> ⚠️ Conflict:" in line for line in adjacent_lines), (
        f"Conflict block not adjacent to claim. Lines after claim: {adjacent_lines}"
    )


# ---------------------------------------------------------------------------
# AC-3.3: No conflict block when no contradiction
# ---------------------------------------------------------------------------

def test_no_contradiction_no_conflict_block_added(tmp_path: Path) -> None:
    """AC-3.3: When the merge result has no conflicts, no conflict block
    appears in the merged page."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    original_content = (
        "# Clean Topic\n\n## Overview\nAll good.\n\n"
        "## Sessions\n> Source: [2026-04-14 sess-a]\n"
    )
    page = _existing_topic_page(wiki_root, "clean-topic", original_content)

    scripted_merge = MergeResult(additions=["An extra detail."], duplicates=[], conflicts=[])
    transcript = _make_transcript(tmp_path, "sess-clean", "more info on clean topic")
    model = FakeModelClient(
        response=json.dumps({"operations": [_topic_op("clean-topic", "All good.")]}),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-clean",
        session_date="2026-04-15",
    )
    assert result.success

    page_text = page.read_text(encoding="utf-8")
    assert "> ⚠️ Conflict:" not in page_text, (
        f"Conflict block added when no contradiction:\n{page_text}"
    )


# ---------------------------------------------------------------------------
# AC-3.4: Affirming session resolves conflict block
# ---------------------------------------------------------------------------

def test_affirming_session_resolves_conflict_block(tmp_path: Path) -> None:
    """AC-3.4: When a subsequent session affirms one side of an existing
    conflict block, the conflict block is removed from the merged page."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import ConflictPair, FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    existing_claim = "X uses port 8080"
    conflict_line = (
        '> ⚠️ Conflict: [Session sess-b] asserts "X uses port 9090" '
        'which contradicts the prior claim above [from Session sess-a].'
    )
    original_content = (
        f"# Service X\n\n## Overview\n{existing_claim}\n"
        f"{conflict_line}\n\n"
        "## Sessions\n> Source: [2026-04-14 sess-a]\n"
        "> Source: [2026-04-15 sess-b]\n"
    )
    page = _existing_topic_page(wiki_root, "service-x", original_content)

    # Affirming session: model affirms the existing claim (port 8080)
    scripted_merge = MergeResult(
        additions=[],
        duplicates=[],
        conflicts=[],
        affirmed_claim=existing_claim,
    )
    transcript = _make_transcript(tmp_path, "sess-c", "confirmed port 8080")
    model = FakeModelClient(
        response=json.dumps({"operations": [_topic_op("service-x", existing_claim)]}),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-c",
        session_date="2026-04-15",
    )
    assert result.success

    page_text = page.read_text(encoding="utf-8")
    assert "> ⚠️ Conflict:" not in page_text, (
        f"Conflict block still present after affirming session:\n{page_text}"
    )
