"""tests/spec_005/test_contradiction_e2e.py — MAJOR-2: end-to-end contradiction surfacing.

Replaces the tautology test in test_cli_extension.py (test_ingest_command_contradiction_surfaced).
Exercises the full pipeline with a FakeModelClient scripted to return a MergeResult with
a real ConflictPair — no monkeypatching of ingest_one.
"""
from __future__ import annotations

import json
import os
import sys
from io import StringIO
from pathlib import Path

import pytest


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


def test_ingest_command_contradiction_surfaced_end_to_end(tmp_path: Path) -> None:
    """AC-7 end-to-end: FakeModelClient scripted with a ConflictPair → CLI reports Contradictions: 1.

    Pipeline:
    1. Wiki has a pre-seeded page asserting "Uses JWT tokens."
    2. FakeModelClient.invoke() returns an op targeting the same page.
    3. FakeModelClient.merge_topic() returns a MergeResult with 1 conflict.
    4. ingest_one detects the conflict, injects the conflict block, populates
       PageResult.contradictions=1.
    5. main() sums contradictions and includes it in IngestSummary.
    6. CLI output contains "Contradictions:     1".
    7. Exit code is 0 (contradiction does not cause failure).
    8. Written page contains a conflict block marker.

    RED: fails until PageResult.contradictions is a real field propagated through
    the pipeline — no monkeypatching of ingest_one allowed.
    """
    from ephemeris import ingest as ingest_mod
    from ephemeris.model import ConflictPair, FakeModelClient, MergeResult

    # --- Setup wiki with pre-seeded page ---
    wiki_root = tmp_path / "wiki"
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    existing_page = topics_dir / "auth-service.md"
    existing_page.write_text(
        "# Auth Service\n\n## Overview\nUses JWT tokens.\n\n## Sessions\n> Source: [2026-04-14 old-sess]\n",
        encoding="utf-8",
    )

    # --- Stage a transcript for the same topic ---
    staging_root = tmp_path / "staging"
    staging_dir = staging_root / "session-end"
    staging_dir.mkdir(parents=True, exist_ok=True)
    transcript = staging_dir / "conflict-sess.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "content": "Auth service now uses basic auth."}) + "\n",
        encoding="utf-8",
    )

    # --- Script FakeModelClient ---
    # invoke() returns an op targeting the pre-existing auth-service topic
    fake_response = json.dumps({
        "operations": [{
            "action": "create",
            "page_type": "topic",
            "page_name": "auth-service",
            "content": {"overview": "Uses basic auth instead of JWT.", "details": ""},
            "cross_references": [],
        }]
    })
    # merge_topic() returns a MergeResult with 1 real ConflictPair
    conflict = ConflictPair(
        existing_claim="Uses JWT tokens.",
        new_claim="Uses basic auth instead of JWT.",
        existing_session_id="old-sess",
        new_session_id="conflict-sess",
    )
    fake_merge = MergeResult(
        additions=[],
        duplicates=[],
        conflicts=[conflict],
    )
    model = FakeModelClient(response=fake_response, merge_result=fake_merge)

    # Patch EPHEMERIS_MODEL_CLIENT won't help here — we need to inject our model.
    # Patch the ingest module's model construction so it uses our scripted FakeModelClient.
    original_fake = ingest_mod.FakeModelClient if hasattr(ingest_mod, "FakeModelClient") else None

    # Approach: monkeypatch FakeModelClient constructor in the ingest module's namespace
    # so that when main() instantiates it, it gets our scripted version.
    class ScriptedFake:
        def __init__(self) -> None:
            pass
        def invoke(self, system_prompt: str, user_prompt: str) -> str:
            return model.invoke(system_prompt, user_prompt)
        def merge_topic(self, existing: str, new: str, session_id: str):
            return model.merge_topic(existing, new, session_id)

    # Patch at the module level so main()'s `from ephemeris.model import FakeModelClient` picks it up
    from ephemeris import model as model_mod
    original_fake_class = model_mod.FakeModelClient
    model_mod.FakeModelClient = ScriptedFake  # type: ignore[assignment]

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
        model_mod.FakeModelClient = original_fake_class  # type: ignore[assignment]

    # Exit code must be 0 — contradictions don't cause failure
    assert code == 0, f"Expected exit 0, got {code}. stderr={err!r}"

    # CLI summary must report 1 contradiction
    assert "Contradictions:     1" in out, (
        f"Expected 'Contradictions:     1' in summary (full output):\n{out!r}"
    )

    # The written page must contain a conflict block
    page_content = existing_page.read_text(encoding="utf-8")
    assert "CONFLICT" in page_content.upper() or "conflict" in page_content.lower(), (
        f"Expected conflict block in written page:\n{page_content!r}"
    )
