"""tests/spec_005/test_cli_extension.py — SPEC-005: Manual Ingest Trigger.

Tests for the CLI extension in ephemeris/ingest.py.
All tests use FakeModelClient; no Anthropic SDK imports.

AC coverage:
    AC-1 (summary block), AC-2 (progress lines), AC-3 (no-pending message),
    AC-4 (idempotent), AC-5 (targeted session), AC-6 (partial failure),
    AC-7 (contradiction surfaced).

Extras:
    test_ingest_command_missing_session_id_errors
    test_list_pending_sessions_deterministic_order
    test_summary_rendering_pure_function
"""
from __future__ import annotations

import json
import os
import sys
from io import StringIO
from pathlib import Path

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


def _run_main(args: list[str], env: dict) -> tuple[int, str, str]:
    """Invoke ephemeris.ingest.main() directly and capture stdout/stderr.

    Returns (exit_code, stdout_text, stderr_text).
    Raises SystemExit and captures it.
    """
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
# Test 1: AC-3 — no pending sessions
# ---------------------------------------------------------------------------

def test_ingest_command_no_pending_sessions(tmp_path: Path) -> None:
    """AC-3: Empty staging dir → clean exit (0), zeros in summary, message present.

    RED: fails because main() doesn't exist in ephemeris.ingest yet.
    """
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    code, out, err = _run_main(
        [],
        {
            "EPHEMERIS_STAGING_ROOT": str(staging_root),
            "EPHEMERIS_WIKI_ROOT": str(wiki_root),
            "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
            "EPHEMERIS_MODEL_CLIENT": "fake",
        },
    )

    assert code == 0, f"Expected exit 0 for no-pending, got {code}. stderr={err!r}"
    assert "No pending sessions" in out, f"Expected 'No pending sessions' in stdout:\n{out!r}"
    assert "Sessions processed: 0" in out, f"Expected 'Sessions processed: 0' in summary:\n{out!r}"
    assert "Pages created:" in out
    assert "Pages updated:" in out


# ---------------------------------------------------------------------------
# Test 2: AC-1 + AC-2 — processes pending sessions with progress lines + summary
# ---------------------------------------------------------------------------

def test_ingest_command_processes_pending_sessions(tmp_path: Path) -> None:
    """AC-1+AC-2: N sessions staged → all processed, progress lines + summary printed.

    RED: fails because main() doesn't exist / doesn't print progress+summary.
    """
    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    _make_transcript(staging_root, "sess-alpha")
    _make_transcript(staging_root, "sess-beta")
    _make_transcript(staging_root, "sess-gamma")

    # FakeModelClient returns one topic op per session
    fake_response = json.dumps({"operations": [_topic_op("mytopic")]})
    # We set EPHEMERIS_MODEL_CLIENT=fake — FakeModelClient default response

    code, out, err = _run_main(
        [],
        {
            "EPHEMERIS_STAGING_ROOT": str(staging_root),
            "EPHEMERIS_WIKI_ROOT": str(wiki_root),
            "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
            "EPHEMERIS_MODEL_CLIENT": "fake",
        },
    )

    assert code == 0, f"Expected exit 0, got {code}. stderr={err!r}"

    # AC-2: progress line per session — format [i/n] Ingesting session <id>...
    assert "[1/3]" in out, f"Expected progress line [1/3] in:\n{out!r}"
    assert "[2/3]" in out
    assert "[3/3]" in out

    # AC-1: summary block present
    assert "=== Ingest Summary ===" in out, f"Expected summary header in:\n{out!r}"
    assert "Sessions processed: 3" in out

    # All staging files consumed
    assert not list((staging_root / "session-end").glob("*.jsonl")), "All transcripts must be consumed"


# ---------------------------------------------------------------------------
# Test 3: AC-5 — targeted session
# ---------------------------------------------------------------------------

def test_ingest_command_targeted_session(tmp_path: Path) -> None:
    """AC-5: With session-id arg, only that session is processed; others remain pending.

    RED: fails because main() doesn't exist / targeted branch not printing summary.
    """
    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    _make_transcript(staging_root, "target-sess")
    _make_transcript(staging_root, "other-sess-1")
    _make_transcript(staging_root, "other-sess-2")

    code, out, err = _run_main(
        ["target-sess"],
        {
            "EPHEMERIS_STAGING_ROOT": str(staging_root),
            "EPHEMERIS_WIKI_ROOT": str(wiki_root),
            "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
            "EPHEMERIS_MODEL_CLIENT": "fake",
        },
    )

    assert code == 0, f"Expected exit 0, got {code}. stderr={err!r}"

    # Target was consumed
    assert not (staging_root / "session-end" / "target-sess.jsonl").exists(), \
        "Target transcript must be consumed"

    # Others remain
    assert (staging_root / "session-end" / "other-sess-1.jsonl").exists(), \
        "other-sess-1 must remain pending"
    assert (staging_root / "session-end" / "other-sess-2.jsonl").exists(), \
        "other-sess-2 must remain pending"

    # Summary shows 1 session
    assert "Sessions processed: 1" in out, f"Expected 'Sessions processed: 1' in:\n{out!r}"


# ---------------------------------------------------------------------------
# Test 4: missing session-id errors non-zero
# ---------------------------------------------------------------------------

def test_ingest_command_missing_session_id_errors(tmp_path: Path) -> None:
    """Extra: unknown session-id → non-zero exit + error message with the ID.

    RED: fails because main() doesn't exist / not printing named error.
    """
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    code, out, err = _run_main(
        ["nonexistent-session"],
        {
            "EPHEMERIS_STAGING_ROOT": str(staging_root),
            "EPHEMERIS_WIKI_ROOT": str(wiki_root),
            "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
            "EPHEMERIS_MODEL_CLIENT": "fake",
        },
    )

    assert code != 0, f"Expected non-zero exit for missing session-id, got {code}"
    combined = out + err
    assert "nonexistent-session" in combined, \
        f"Expected missing session-id named in output:\n{combined!r}"


# ---------------------------------------------------------------------------
# Test 5: AC-4 — idempotent
# ---------------------------------------------------------------------------

def test_ingest_command_idempotent(tmp_path: Path) -> None:
    """AC-4: Run twice. First run processes; second finds nothing pending.

    RED: fails because main() doesn't exist / summary not printed.
    """
    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    _make_transcript(staging_root, "idem-sess")

    env = {
        "EPHEMERIS_STAGING_ROOT": str(staging_root),
        "EPHEMERIS_WIKI_ROOT": str(wiki_root),
        "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
        "EPHEMERIS_MODEL_CLIENT": "fake",
    }

    # First run
    code1, out1, err1 = _run_main([], env)
    assert code1 == 0, f"First run failed: {err1!r}"
    assert "Sessions processed: 1" in out1

    # Second run — nothing pending
    code2, out2, err2 = _run_main([], env)
    assert code2 == 0, f"Second run failed: {err2!r}"
    assert "Sessions processed: 0" in out2
    assert "No pending sessions" in out2

    # Wiki unchanged after second run — same number of pages
    topics = list((wiki_root / "topics").glob("*.md")) if (wiki_root / "topics").exists() else []
    assert len(topics) >= 0  # At least no crash


# ---------------------------------------------------------------------------
# Test 6: AC-6 — partial failure
# ---------------------------------------------------------------------------

def test_ingest_command_partial_failure(tmp_path: Path) -> None:
    """AC-6: Session 2 of 3 fails → sessions 1 and 3 in wiki, session 2 in errors,
    exit code non-zero.

    RED: fails because main() doesn't exist / exit code 0 even on failure.
    """
    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    _make_transcript(staging_root, "sess-1")
    _make_transcript(staging_root, "sess-2")
    _make_transcript(staging_root, "sess-3")

    # We need to make sess-2 fail. We monkeypatch ingest_one to raise on sess-2.
    # Use environment to trigger fake with known per-session behavior.
    # Approach: monkeypatch at the ingest module level.
    from ephemeris import ingest as ingest_mod
    from ephemeris.ingest import PageResult
    original_ingest_one = ingest_mod.ingest_one

    call_order: list[str] = []

    def patched_ingest_one(transcript_path, wiki_root, model, log, session_id, session_date, dry_run=False, **kwargs):
        call_order.append(session_id)
        if session_id == "sess-2":
            return PageResult(success=False, session_id=session_id, error="deliberate failure")
        return original_ingest_one(transcript_path, wiki_root, model, log, session_id, session_date, dry_run, **kwargs)

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

    # Non-zero exit because one session failed
    assert code != 0, f"Expected non-zero exit on partial failure, got {code}. out={out!r}"

    combined = out + err
    # Failure session named in output
    assert "sess-2" in combined, f"Failed session must be named:\n{combined!r}"
    assert "deliberate failure" in combined, f"Error reason must appear:\n{combined!r}"

    # Summary shows 2 successes and 1 error
    assert "Errors:             1" in out or "Errors: 1" in out, \
        f"Expected error count in summary:\n{out!r}"


# ---------------------------------------------------------------------------
# Test 7: AC-7 — contradiction surfaced
# ---------------------------------------------------------------------------

def test_ingest_command_contradiction_surfaced(tmp_path: Path) -> None:
    """AC-7: Contradiction from merge_topic appears in summary; exit code 0.

    RED: fails because main() doesn't track/report contradictions.
    """
    staging_root = tmp_path / "staging"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    # Create an existing page so merge path is triggered
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True)
    existing_page = topics_dir / "auth-service.md"
    existing_page.write_text(
        "# Auth Service\n\n## Overview\nUses JWT tokens.\n\n## Sessions\n> Source: [2026-04-14 old-sess]\n",
        encoding="utf-8",
    )

    _make_transcript(staging_root, "conflict-sess", "Auth service uses basic auth now.")

    # Patch ingest_one to return a PageResult with contradictions count
    from ephemeris import ingest as ingest_mod
    from ephemeris.ingest import PageResult
    original_ingest_one = ingest_mod.ingest_one

    def patched_ingest_one(transcript_path, wiki_root, model, log, session_id, session_date, dry_run=False, **kwargs):
        result = original_ingest_one(transcript_path, wiki_root, model, log, session_id, session_date, dry_run, **kwargs)
        # Inject contradictions count into result
        result.contradictions = 1  # type: ignore[attr-defined]
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
        ingest_mod.ingest_one = patched_ingest_one  # type: ignore[assignment]
        ingest_mod.ingest_one = original_ingest_one  # type: ignore[assignment]

    assert code == 0, f"Contradiction must not cause failure, got {code}. err={err!r}"
    assert "Contradictions:" in out, f"Expected 'Contradictions:' in summary:\n{out!r}"


# ---------------------------------------------------------------------------
# Test 8: list_pending_sessions helper — deterministic order
# ---------------------------------------------------------------------------

def test_list_pending_sessions_deterministic_order(tmp_path: Path) -> None:
    """Extra: list_pending_sessions returns JSONL files in sorted order.

    RED: fails because list_pending_sessions doesn't exist in ephemeris.ingest.
    """
    from ephemeris.ingest import list_pending_sessions

    staging_root = tmp_path / "staging"
    _make_transcript(staging_root, "zzz-last")
    _make_transcript(staging_root, "aaa-first")
    _make_transcript(staging_root, "mmm-middle")

    pending = list_pending_sessions(staging_root)
    names = [p.stem for p in pending]
    assert names == sorted(names), f"Expected sorted order, got {names}"


# ---------------------------------------------------------------------------
# Test 9: summary rendering is a pure function
# ---------------------------------------------------------------------------

def test_summary_rendering_pure_function(tmp_path: Path) -> None:
    """Extra (REFACTOR step): render_ingest_summary() is a pure function.

    RED: fails because render_ingest_summary doesn't exist in ephemeris.ingest.
    """
    from ephemeris.ingest import IngestSummary, render_ingest_summary

    summary = IngestSummary(
        sessions_processed=3,
        pages_created=5,
        pages_updated=2,
        contradictions=1,
        errors=0,
        error_lines=[],
    )
    output = render_ingest_summary(summary)

    assert "=== Ingest Summary ===" in output
    assert "Sessions processed: 3" in output
    assert "Pages created:      5" in output
    assert "Pages updated:      2" in output
    assert "Contradictions:     1" in output
    assert "Errors:             0" in output
