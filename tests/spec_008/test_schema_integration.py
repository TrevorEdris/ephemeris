"""tests/spec_008/test_schema_integration.py — SPEC-008: Custom Wiki Schema.

Integration tests for schema resolution wired into the ingestion pipeline.
All tests use FakeModelClient; no Anthropic SDK imports.

AC coverage:
    AC-2 (valid user schema injected into ingestion system_prompt)
    AC-6 (default-schema wiki pages preserved after user-schema run)
    AC-7 (user-schema wiki pages preserved after default-schema run)
    AC-9 (schema file read at most once per multi-session ingest run)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
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


# ---------------------------------------------------------------------------
# AC-2: valid user schema injected into system prompt during ingestion
# ---------------------------------------------------------------------------

def test_ingest_one_uses_user_schema_in_prompt(tmp_path: Path) -> None:
    """AC-2: When resolve_schema returns user schema content, that content appears
    in the system_prompt passed to the model.

    RED: fails because ingest_one doesn't call resolve_schema yet.
    """
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    staging = tmp_path / "staging" / "session-end"
    staging.mkdir(parents=True)

    transcript_path = staging / "test-sess.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "user", "content": "Talk about recipes."}) + "\n",
        encoding="utf-8",
    )

    user_schema_content = "# My Cooking Wiki Schema\nPage type: cooking-recipe\n"
    schema_file = tmp_path / "schema.md"
    schema_file.write_text(user_schema_content, encoding="utf-8")

    captured_prompts: list[str] = []

    class CapturingFakeClient(FakeModelClient):
        def invoke(self, system_prompt: str, user_prompt: str) -> str:
            captured_prompts.append(system_prompt)
            return '{"operations": []}'

    log = IngestLogger(tmp_path / "test.log")

    from ephemeris.schema import resolve_schema
    resolved = resolve_schema(wiki_root, user_schema_path=schema_file)

    ingest_one(
        transcript_path=transcript_path,
        wiki_root=wiki_root,
        model=CapturingFakeClient(),
        log=log,
        session_id="test-sess",
        session_date="2026-04-15",
        schema_text=resolved,
    )

    assert captured_prompts, "Model.invoke was never called"
    system_prompt = captured_prompts[0]
    assert "## Wiki Schema" in system_prompt
    assert "My Cooking Wiki Schema" in system_prompt
    assert "cooking-recipe" in system_prompt


# ---------------------------------------------------------------------------
# AC-6: default-schema pages preserved after user-schema run
# ---------------------------------------------------------------------------

def test_schema_switch_default_to_user_preserves_pages(tmp_path: Path) -> None:
    """AC-6: Pages written during a default-schema run are present and unmodified
    after a subsequent user-schema ingestion run on the same wiki.

    RED: fails because ingest_one doesn't accept / use schema_text parameter yet.
    """
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient
    from ephemeris.schema import DEFAULT_SCHEMA, resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log = IngestLogger(tmp_path / "test.log")

    # --- Run 1: default schema ---
    staging1 = tmp_path / "staging1" / "session-end"
    staging1.mkdir(parents=True)
    t1 = staging1 / "sess-default.jsonl"
    t1.write_text(
        json.dumps({"type": "user", "content": "Discuss caching strategy."}) + "\n",
        encoding="utf-8",
    )
    page_name = "caching-strategy"
    fake_response = json.dumps({"operations": [_topic_op(page_name)]})

    ingest_one(
        transcript_path=t1,
        wiki_root=wiki_root,
        model=FakeModelClient(response=fake_response),
        log=log,
        session_id="sess-default",
        session_date="2026-04-15",
        schema_text=DEFAULT_SCHEMA,
    )

    page_path = wiki_root / "topics" / f"{page_name}.md"
    assert page_path.exists(), "Topic page must be created after default-schema run"
    original_content = page_path.read_text(encoding="utf-8")

    # --- Run 2: user schema ---
    staging2 = tmp_path / "staging2" / "session-end"
    staging2.mkdir(parents=True)
    t2 = staging2 / "sess-user.jsonl"
    t2.write_text(
        json.dumps({"type": "user", "content": "New session with different schema."}) + "\n",
        encoding="utf-8",
    )

    user_schema = tmp_path / "user-schema.md"
    user_schema.write_text("# Custom Schema\nDifferent page types.\n", encoding="utf-8")
    user_schema_text = resolve_schema(wiki_root, user_schema_path=user_schema)

    ingest_one(
        transcript_path=t2,
        wiki_root=wiki_root,
        model=FakeModelClient(response='{"operations": []}'),
        log=log,
        session_id="sess-user",
        session_date="2026-04-15",
        schema_text=user_schema_text,
    )

    # Original page must still exist, unmodified
    assert page_path.exists(), "Original page must still exist after user-schema run"
    assert page_path.read_text(encoding="utf-8") == original_content, \
        "Original page content must be unchanged after user-schema run"


# ---------------------------------------------------------------------------
# AC-7: user-schema pages preserved after default-schema run
# ---------------------------------------------------------------------------

def test_schema_switch_user_to_default_preserves_pages(tmp_path: Path) -> None:
    """AC-7: Pages written during a user-schema run are present and unmodified
    after a subsequent default-schema ingestion run on the same wiki.

    RED: fails because ingest_one doesn't accept / use schema_text parameter yet.
    """
    from ephemeris.ingest import ingest_one
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient
    from ephemeris.schema import DEFAULT_SCHEMA, resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    log = IngestLogger(tmp_path / "test.log")

    user_schema = tmp_path / "user-schema.md"
    user_schema.write_text("# Custom Schema\nSpecialized types.\n", encoding="utf-8")
    user_schema_text = resolve_schema(wiki_root, user_schema_path=user_schema)

    # --- Run 1: user schema ---
    staging1 = tmp_path / "staging1" / "session-end"
    staging1.mkdir(parents=True)
    t1 = staging1 / "sess-user.jsonl"
    t1.write_text(
        json.dumps({"type": "user", "content": "Discuss deployment pipeline."}) + "\n",
        encoding="utf-8",
    )
    page_name = "deployment-pipeline"
    fake_response = json.dumps({"operations": [_topic_op(page_name)]})

    ingest_one(
        transcript_path=t1,
        wiki_root=wiki_root,
        model=FakeModelClient(response=fake_response),
        log=log,
        session_id="sess-user",
        session_date="2026-04-15",
        schema_text=user_schema_text,
    )

    page_path = wiki_root / "topics" / f"{page_name}.md"
    assert page_path.exists(), "Topic page must be created after user-schema run"
    original_content = page_path.read_text(encoding="utf-8")

    # --- Run 2: default schema ---
    staging2 = tmp_path / "staging2" / "session-end"
    staging2.mkdir(parents=True)
    t2 = staging2 / "sess-default.jsonl"
    t2.write_text(
        json.dumps({"type": "user", "content": "Another session with default schema."}) + "\n",
        encoding="utf-8",
    )

    ingest_one(
        transcript_path=t2,
        wiki_root=wiki_root,
        model=FakeModelClient(response='{"operations": []}'),
        log=log,
        session_id="sess-default",
        session_date="2026-04-15",
        schema_text=DEFAULT_SCHEMA,
    )

    # Original page must still exist, unmodified
    assert page_path.exists(), "Original page must still exist after default-schema run"
    assert page_path.read_text(encoding="utf-8") == original_content, \
        "Original page content must be unchanged after default-schema run"


# ---------------------------------------------------------------------------
# AC-9: schema file read at most once per multi-session ingest run
# ---------------------------------------------------------------------------

def test_ingest_all_reads_schema_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-9: ingest_all resolves schema once and passes it into each ingest_one call;
    the schema file is read at most once per run even when processing multiple sessions.

    RED: fails because ingest_all doesn't resolve schema once and pass it through.
    """
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    staging_root = tmp_path / "staging"

    # Stage 3 transcripts
    _make_transcript(staging_root, "sess-a")
    _make_transcript(staging_root, "sess-b")
    _make_transcript(staging_root, "sess-c")

    schema_file = tmp_path / "schema.md"
    schema_file.write_text("# Test Schema\nFor counting reads.\n", encoding="utf-8")

    read_count: list[int] = [0]
    original_read_text = Path.read_text

    def counting_read_text(self: Path, *args, **kwargs) -> str:  # type: ignore[override]
        if self == schema_file:
            read_count[0] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    log = IngestLogger(tmp_path / "test.log")

    monkeypatch.setenv("EPHEMERIS_SCHEMA_PATH", str(schema_file))

    ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=FakeModelClient(),
        log=log,
    )

    assert read_count[0] == 1, (
        f"Schema file must be read exactly once per ingest_all run, "
        f"but was read {read_count[0]} time(s)"
    )
