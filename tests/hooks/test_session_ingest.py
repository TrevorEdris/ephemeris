"""Tests for the session_ingest UserPromptSubmit hook.

The hook finds the most recent past session (not today's) under
EPHEMERIS_SESSIONS_ROOT, checks it has DISCOVERY.md or PLAN.md, and — if the
session is not yet marked as ingested in the state file — injects an
additionalContext instruction telling the LLM to run the /ingest script.

State file: $EPHEMERIS_STATE_ROOT/ingested-sessions.json
Default state root: ~/.ai/ephemeris/state/
"""

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session_ingest.py"


def run_hook(sessions_root: Path, state_root: Path) -> dict:
    env = os.environ.copy()
    env["EPHEMERIS_SESSIONS_ROOT"] = str(sessions_root)
    env["EPHEMERIS_STATE_ROOT"] = str(state_root)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert result.returncode == 0, f"hook failed: {result.stderr}"
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def make_session(root: Path, day_offset: int, slug: str, files: list[str]) -> Path:
    day = (date.today() + timedelta(days=day_offset)).isoformat()
    d = root / f"{day}_{slug}"
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_text(f"# {f}\n\ncontent\n")
    return d


def test_no_past_session_emits_empty_context(tmp_path):
    sessions = tmp_path / "sessions"
    state = tmp_path / "state"
    sessions.mkdir()
    make_session(sessions, 0, "today", ["SESSION.md", "DISCOVERY.md"])
    out = run_hook(sessions, state)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert ctx == ""


def test_past_session_with_discovery_triggers_ingest(tmp_path):
    sessions = tmp_path / "sessions"
    state = tmp_path / "state"
    sessions.mkdir()
    make_session(sessions, -1, "yesterday", ["SESSION.md", "DISCOVERY.md"])
    out = run_hook(sessions, state)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "ingest_sessions.py" in ctx
    assert "yesterday" in ctx


def test_past_session_without_discovery_is_skipped(tmp_path):
    sessions = tmp_path / "sessions"
    state = tmp_path / "state"
    sessions.mkdir()
    make_session(sessions, -1, "slug", ["SESSION.md"])  # no DISCOVERY / PLAN
    out = run_hook(sessions, state)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert ctx == ""


def test_past_session_already_ingested_is_skipped(tmp_path):
    sessions = tmp_path / "sessions"
    state = tmp_path / "state"
    sessions.mkdir()
    state.mkdir()
    d = make_session(sessions, -1, "done", ["SESSION.md", "PLAN.md"])
    # Pre-populate state file as if /ingest had already run
    (state / "ingested-sessions.json").write_text(json.dumps([d.name]))
    out = run_hook(sessions, state)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert ctx == ""


def test_picks_most_recent_past_session(tmp_path):
    sessions = tmp_path / "sessions"
    state = tmp_path / "state"
    sessions.mkdir()
    old_dir = make_session(sessions, -5, "aaa", ["PLAN.md"])
    new_dir = make_session(sessions, -1, "zzz", ["PLAN.md"])
    out = run_hook(sessions, state)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert new_dir.name in ctx
    assert old_dir.name not in ctx


def test_missing_sessions_root_is_safe(tmp_path):
    sessions = tmp_path / "nonexistent"
    state = tmp_path / "state"
    out = run_hook(sessions, state)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert ctx == ""


def test_state_dir_auto_created(tmp_path):
    """Hook should create the state dir if absent — no crash on first run."""
    sessions = tmp_path / "sessions"
    state = tmp_path / "state"  # not pre-created
    sessions.mkdir()
    make_session(sessions, -1, "slug", ["DISCOVERY.md"])
    out = run_hook(sessions, state)
    assert state.exists()
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "slug" in ctx
