"""tests/spec_008/test_schema_integration.py — SPEC-008: Custom Wiki Schema.

Integration tests for schema resolution wired into the ingestion pipeline.
All tests use FakeModelClient; no Anthropic SDK imports.

AC coverage:
    AC-2 (valid user schema injected into ingestion system_prompt)
    AC-2 production (auto-discovery of ~/.claude/ephemeris/schema.md via run_ingest_all)
    AC-6 (default-schema wiki pages preserved after user-schema run)
    AC-7 (user-schema wiki pages preserved after default-schema run)
    AC-9 (schema file read at most once per multi-session ingest run)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

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


def test_ingest_all_reads_schema_file_once_via_production_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-9 production path: ingest_all reads the user_schema_path (Path.home()-based)
    file exactly once even when processing multiple sessions, without EPHEMERIS_SCHEMA_PATH.

    This exercises the production wiring where resolve_schema is called with the
    user_schema_path kwarg (not the env var seam).
    """
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    # Ensure env var is NOT set — exercises the user_schema_path production path
    monkeypatch.delenv("EPHEMERIS_SCHEMA_PATH", raising=False)

    # Fake HOME: place schema at the well-known path
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    schema_dir = fake_home / ".claude" / "ephemeris"
    schema_dir.mkdir(parents=True)
    schema_file = schema_dir / "schema.md"
    schema_file.write_text("# Production Path Schema\nFor read-count testing.\n", encoding="utf-8")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    staging_root = tmp_path / "staging"

    # Stage 3 transcripts — schema must be read exactly once regardless of count
    _make_transcript(staging_root, "prod-sess-a")
    _make_transcript(staging_root, "prod-sess-b")
    _make_transcript(staging_root, "prod-sess-c")

    read_count: list[int] = [0]
    original_read_text = Path.read_text

    def counting_read_text(self: Path, *args, **kwargs) -> str:  # type: ignore[override]
        if self == schema_file:
            read_count[0] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    log = IngestLogger(tmp_path / "test.log")

    ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=FakeModelClient(),
        log=log,
    )

    assert read_count[0] == 1, (
        f"Schema file must be read exactly once per ingest_all run via production path, "
        f"but was read {read_count[0]} time(s)"
    )


# ---------------------------------------------------------------------------
# AC-2 production: ingest_all auto-discovers ~/.claude/ephemeris/schema.md
# ---------------------------------------------------------------------------

def test_ingest_all_auto_discovers_user_schema_without_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2 production path: when ~/.claude/ephemeris/schema.md exists,
    ingest_all injects it into the system_prompt WITHOUT requiring
    EPHEMERIS_SCHEMA_PATH to be set.

    Strategy:
    - Use tmp_path as a fake HOME by monkeypatching Path.home()
    - Write schema with unique marker at <tmp_path>/.claude/ephemeris/schema.md
    - Run ingest_all with a CapturingFakeClient that records system_prompt
    - Assert marker appears in the captured prompt
    - EPHEMERIS_SCHEMA_PATH is explicitly unset to prove auto-discovery works
    """
    from ephemeris.ingest import ingest_all
    from ephemeris.log import IngestLogger
    from ephemeris.model import FakeModelClient

    # Ensure EPHEMERIS_SCHEMA_PATH is NOT set — prove auto-discovery path
    monkeypatch.delenv("EPHEMERIS_SCHEMA_PATH", raising=False)

    # Fake HOME: write well-known schema path under tmp_path
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    schema_dir = fake_home / ".claude" / "ephemeris"
    schema_dir.mkdir(parents=True)
    schema_file = schema_dir / "schema.md"
    schema_file.write_text(
        "# Auto-Discovered Schema\nUNIQUE_AC2_MARKER_XYZ\n",
        encoding="utf-8",
    )

    # Monkeypatch Path.home() so expanduser("~") resolves to fake_home
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    staging_root = tmp_path / "staging"

    _make_transcript(staging_root, "ac2-prod-sess")

    captured_prompts: list[str] = []

    class CapturingFakeClient(FakeModelClient):
        def invoke(self, system_prompt: str, user_prompt: str) -> str:
            captured_prompts.append(system_prompt)
            return '{"operations": []}'

    log = IngestLogger(tmp_path / "test.log")

    ingest_all(
        staging_root=staging_root,
        wiki_root=wiki_root,
        model=CapturingFakeClient(),
        log=log,
    )

    assert captured_prompts, "Model.invoke was never called — no transcripts processed"
    system_prompt = captured_prompts[0]
    assert "UNIQUE_AC2_MARKER_XYZ" in system_prompt, (
        "Auto-discovered user schema marker must appear in system_prompt. "
        f"Got prompt starting with: {system_prompt[:200]!r}"
    )


# ---------------------------------------------------------------------------
# BLOCKER AC-2 single-session: main() single-session mode auto-discovers schema
# ---------------------------------------------------------------------------

def test_main_single_session_auto_discovers_user_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BLOCKER AC-2: When main() is invoked with a single session_id argument,
    it auto-discovers ~/.claude/ephemeris/schema.md and passes it to ingest_one.

    RED: fails because main() single-session branch does not call resolve_schema
    and never passes schema_text to ingest_one.
    """
    from ephemeris.ingest import main
    from ephemeris.model import FakeModelClient

    # Ensure EPHEMERIS_SCHEMA_PATH is NOT set — prove auto-discovery path
    monkeypatch.delenv("EPHEMERIS_SCHEMA_PATH", raising=False)

    # Fake HOME: write well-known schema path under tmp_path
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    schema_dir = fake_home / ".claude" / "ephemeris"
    schema_dir.mkdir(parents=True)
    schema_file = schema_dir / "schema.md"
    schema_file.write_text(
        "# Single-Session Auto-Discovery Schema\nUNIQUE_AC2_SINGLE_SESSION_MARKER\n",
        encoding="utf-8",
    )

    # Monkeypatch Path.home() so resolve_schema finds the fake schema
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    # Set up staging root with a transcript for the target session
    staging_root = tmp_path / "staging"
    session_id = "single-sess-ac2"
    transcript_path = _make_transcript(staging_root, session_id)

    monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
    monkeypatch.setenv("EPHEMERIS_WIKI_ROOT", str(tmp_path / "wiki"))
    monkeypatch.setenv("EPHEMERIS_LOG_PATH", str(tmp_path / "test.log"))
    monkeypatch.setenv("EPHEMERIS_MODEL_CLIENT", "fake")

    (tmp_path / "wiki").mkdir(parents=True, exist_ok=True)

    captured_prompts: list[str] = []

    class CapturingFakeClient(FakeModelClient):
        def invoke(self, system_prompt: str, user_prompt: str) -> str:
            captured_prompts.append(system_prompt)
            return '{"operations": []}'

    # Monkeypatch FakeModelClient in the ephemeris.ingest module so main() picks it up
    monkeypatch.setattr("ephemeris.model.FakeModelClient", CapturingFakeClient)

    main([session_id])

    assert captured_prompts, "Model.invoke was never called"
    system_prompt = captured_prompts[0]
    assert "UNIQUE_AC2_SINGLE_SESSION_MARKER" in system_prompt, (
        "Auto-discovered user schema marker must appear in single-session system_prompt. "
        f"Got prompt starting with: {system_prompt[:200]!r}"
    )
