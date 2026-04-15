"""tests/spec_004/test_merge.py — Slice 2: Merge Without Duplication.

AC-2.1: Single page for overlapping topic after 2nd session.
AC-2.2: No duplicate claims in merged page.
AC-2.3: New fact appended to existing page.
AC-2.4: New topic creates new page (no regression from SPEC-003).
Safety: Duplicate-only session leaves page byte-for-byte unchanged.
Regression: Merge preserves cross-references from existing page.
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


def _topic_op(name: str, overview: str, details: str = "") -> dict:
    return {
        "action": "create",
        "page_type": "topic",
        "page_name": name,
        "content": {"overview": overview, "details": details},
        "cross_references": [],
    }


def _existing_topic_page(wiki_root: Path, name: str, content: str) -> Path:
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    page = topics_dir / f"{name}.md"
    page.write_text(content, encoding="utf-8")
    return page


# ---------------------------------------------------------------------------
# Data model tests — MergeResult, ConflictPair must exist on ephemeris.model
# ---------------------------------------------------------------------------

def test_merge_result_dataclass_exists() -> None:
    """MergeResult and ConflictPair must be importable from ephemeris.model."""
    from ephemeris.model import ConflictPair, MergeResult  # RED: not yet defined

    mr = MergeResult(additions=["fact A"], duplicates=["fact B"], conflicts=[])
    assert mr.additions == ["fact A"]
    assert mr.duplicates == ["fact B"]
    assert mr.conflicts == []


def test_conflict_pair_dataclass_fields() -> None:
    """ConflictPair must have four fields: existing_claim, new_claim,
    existing_session_id, new_session_id."""
    from ephemeris.model import ConflictPair

    cp = ConflictPair(
        existing_claim="X uses port 8080",
        new_claim="X uses port 9090",
        existing_session_id="sess-a",
        new_session_id="sess-b",
    )
    assert cp.existing_claim == "X uses port 8080"
    assert cp.new_claim == "X uses port 9090"
    assert cp.existing_session_id == "sess-a"
    assert cp.new_session_id == "sess-b"


def test_fake_model_client_has_merge_topic() -> None:
    """FakeModelClient must support merge_topic returning a MergeResult."""
    from ephemeris.model import ConflictPair, FakeModelClient, MergeResult

    fake = FakeModelClient()
    result = fake.merge_topic(
        existing="Old content.", new="New content.", session_id="sess-x"
    )
    assert isinstance(result, MergeResult)


def test_fake_model_client_scriptable_merge_response() -> None:
    """FakeModelClient.merge_topic must return a pre-configured MergeResult."""
    from ephemeris.model import ConflictPair, FakeModelClient, MergeResult

    scripted = MergeResult(
        additions=["net-new fact"],
        duplicates=["already present"],
        conflicts=[],
    )
    fake = FakeModelClient(merge_result=scripted)
    result = fake.merge_topic(
        existing="Already present.", new="Net-new fact.", session_id="sess-y"
    )
    assert result.additions == ["net-new fact"]
    assert result.duplicates == ["already present"]
    assert result.conflicts == []


# ---------------------------------------------------------------------------
# AC-2.1: Single page for overlapping topic
# ---------------------------------------------------------------------------

def test_new_session_overlapping_topic_produces_single_page(tmp_path: Path) -> None:
    """AC-2.1: Session A creates topic-t; session B also covers topic-t.
    After session B ingestion, exactly one page exists for topic-t."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    # Session A — creates the page from scratch
    transcript_a = _make_transcript(tmp_path, "sess-a", "Discuss topic-t.")
    model_a = FakeModelClient(response=json.dumps({
        "operations": [_topic_op("topic-t", "Session A overview.")]
    }))
    result_a = ingest_one(
        transcript_path=transcript_a,
        wiki_root=wiki_root,
        model=model_a,
        log=IngestLogger(log_path),
        session_id="sess-a",
        session_date="2026-04-15",
    )
    assert result_a.success

    # Session B — overlapping topic; merge returns only duplicates (no new content)
    scripted_merge = MergeResult(
        additions=[], duplicates=["Session A overview."], conflicts=[]
    )
    transcript_b = _make_transcript(tmp_path, "sess-b", "Also discuss topic-t.")
    model_b = FakeModelClient(
        response=json.dumps({
            "operations": [_topic_op("topic-t", "Session A overview.")]
        }),
        merge_result=scripted_merge,
    )
    result_b = ingest_one(
        transcript_path=transcript_b,
        wiki_root=wiki_root,
        model=model_b,
        log=IngestLogger(log_path),
        session_id="sess-b",
        session_date="2026-04-15",
    )
    assert result_b.success

    # Exactly one page for topic-t
    topic_pages = list((wiki_root / "topics").glob("topic-t*.md"))
    assert len(topic_pages) == 1, f"Expected 1 page, found {len(topic_pages)}: {topic_pages}"


# ---------------------------------------------------------------------------
# AC-2.2: No duplicate claims
# ---------------------------------------------------------------------------

def test_repeated_claim_not_duplicated(tmp_path: Path) -> None:
    """AC-2.2: If session B repeats a claim already in the wiki page,
    the merged page does not contain duplicate instances."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    existing_claim = "Service uses gRPC for inter-process communication."
    _existing_topic_page(
        wiki_root,
        "service-arch",
        f"# Service Arch\n\n## Overview\n{existing_claim}\n\n## Sessions\n> Source: [2026-04-14 sess-old]\n",
    )

    # Session repeats the claim — merge marks it as duplicate
    scripted_merge = MergeResult(
        additions=[],
        duplicates=[existing_claim],
        conflicts=[],
    )
    transcript = _make_transcript(tmp_path, "sess-repeat", "service uses gRPC")
    model = FakeModelClient(
        response=json.dumps({
            "operations": [_topic_op("service-arch", existing_claim)]
        }),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-repeat",
        session_date="2026-04-15",
    )
    assert result.success

    page_text = (wiki_root / "topics" / "service-arch.md").read_text(encoding="utf-8")
    count = page_text.count(existing_claim)
    assert count == 1, f"Claim appears {count} times (expected 1)"


# ---------------------------------------------------------------------------
# AC-2.3: New fact appended
# ---------------------------------------------------------------------------

def test_new_fact_appended_to_existing_page(tmp_path: Path) -> None:
    """AC-2.3: When session B adds a genuinely new fact, the merged page
    includes that fact."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    existing_content = "# Cache Layer\n\n## Overview\nUses Redis.\n\n## Sessions\n> Source: [2026-04-14 sess-old]\n"
    _existing_topic_page(wiki_root, "cache-layer", existing_content)

    new_fact = "Cache TTL is configured to 300 seconds."
    scripted_merge = MergeResult(
        additions=[new_fact],
        duplicates=[],
        conflicts=[],
    )
    transcript = _make_transcript(tmp_path, "sess-newfact", "cache TTL 300s")
    model = FakeModelClient(
        response=json.dumps({
            "operations": [_topic_op("cache-layer", "Uses Redis.", new_fact)]
        }),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-newfact",
        session_date="2026-04-15",
    )
    assert result.success

    page_text = (wiki_root / "topics" / "cache-layer.md").read_text(encoding="utf-8")
    assert new_fact in page_text, f"New fact not found in merged page:\n{page_text}"


# ---------------------------------------------------------------------------
# AC-2.4: New topic regression (no existing page → create as before)
# ---------------------------------------------------------------------------

def test_new_topic_creates_new_page_no_regression(tmp_path: Path) -> None:
    """AC-2.4: When a session covers a topic with no existing wiki page,
    a new page is created exactly as in SPEC-003 (no merge call)."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    # merge_result is never-called when page doesn't exist
    scripted_merge = MergeResult(
        additions=["should not appear"],
        duplicates=[],
        conflicts=[],
    )
    transcript = _make_transcript(tmp_path, "sess-new", "brand new topic")
    model = FakeModelClient(
        response=json.dumps({
            "operations": [_topic_op("brand-new-topic", "First time this topic appears.")]
        }),
        merge_result=scripted_merge,  # should NOT be invoked
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-new",
        session_date="2026-04-15",
    )
    assert result.success

    page = wiki_root / "topics" / "brand-new-topic.md"
    assert page.exists(), "New topic page was not created"
    text = page.read_text(encoding="utf-8")
    assert "First time this topic appears." in text
    # merge addition should NOT appear (no merge was called)
    assert "should not appear" not in text


# ---------------------------------------------------------------------------
# Safety: duplicate-only session leaves page byte-for-byte unchanged
# ---------------------------------------------------------------------------

def test_duplicate_only_session_leaves_page_unchanged_byte_for_byte(tmp_path: Path) -> None:
    """When the merge result has only duplicates and no additions/conflicts,
    the page on disk must be byte-for-byte identical to the pre-run state."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    original_content = "# My Topic\n\n## Overview\nExisting fact.\n\n## Sessions\n> Source: [2026-04-14 sess-old]\n"
    page = _existing_topic_page(wiki_root, "my-topic", original_content)
    original_bytes = page.read_bytes()

    scripted_merge = MergeResult(
        additions=[], duplicates=["Existing fact."], conflicts=[]
    )
    transcript = _make_transcript(tmp_path, "sess-dup", "repeat existing fact")
    model = FakeModelClient(
        response=json.dumps({
            "operations": [_topic_op("my-topic", "Existing fact.")]
        }),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-dup",
        session_date="2026-04-15",
    )
    assert result.success

    assert page.read_bytes() == original_bytes, (
        "Page was modified when merge result had only duplicates"
    )


# ---------------------------------------------------------------------------
# Regression: merge preserves cross-references from existing page
# ---------------------------------------------------------------------------

def test_merge_preserves_cross_references_from_existing_page(tmp_path: Path) -> None:
    """Merging into an existing page must not strip existing cross-reference links."""
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient, MergeResult

    wiki_root = tmp_path / "wiki"
    log_path = tmp_path / "ingest.log"

    cross_ref_line = "- [OtherTopic](../topics/other-topic.md)"
    original_content = (
        "# My Topic\n\n## Overview\nExisting fact.\n\n"
        "## See Also\n" + cross_ref_line + "\n\n"
        "## Sessions\n> Source: [2026-04-14 sess-old]\n"
    )
    page = _existing_topic_page(wiki_root, "my-topic", original_content)

    new_fact = "A truly new fact."
    scripted_merge = MergeResult(
        additions=[new_fact], duplicates=["Existing fact."], conflicts=[]
    )
    transcript = _make_transcript(tmp_path, "sess-xref", "add new fact to my-topic")
    model = FakeModelClient(
        response=json.dumps({
            "operations": [_topic_op("my-topic", "Existing fact.", new_fact)]
        }),
        merge_result=scripted_merge,
    )

    result = ingest_one(
        transcript_path=transcript,
        wiki_root=wiki_root,
        model=model,
        log=IngestLogger(log_path),
        session_id="sess-xref",
        session_date="2026-04-15",
    )
    assert result.success

    page_text = page.read_text(encoding="utf-8")
    assert cross_ref_line in page_text, (
        f"Cross-reference was stripped from merged page:\n{page_text}"
    )
    assert new_fact in page_text
