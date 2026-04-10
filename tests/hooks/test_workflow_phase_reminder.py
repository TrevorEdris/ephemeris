"""Tests for the workflow_phase_reminder UserPromptSubmit hook.

The hook inspects the current session directory under ~/src/.ai/sessions/ and
emits JSON on stdout with a brief phase-specific reminder in additionalContext.

Phase detection rules (conservative — only inject when exactly one phase matches):
    no session dir         -> inject "Create session directory"
    SESSION.md only        -> Discover
    DISCOVERY.md present   -> Plan
    PLAN.md present        -> Implement
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "workflow_phase_reminder.py"


def run_hook(sessions_root: Path) -> dict:
    """Invoke the hook with EPHEMERIS_SESSIONS_ROOT pointing at a tmp dir."""
    env = os.environ.copy()
    env["EPHEMERIS_SESSIONS_ROOT"] = str(sessions_root)
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


def make_session(sessions_root: Path, slug: str, files: list[str]) -> Path:
    today = date.today().isoformat()
    d = sessions_root / f"{today}_{slug}"
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_text(f"# {f}\n")
    return d


def test_no_session_dir(tmp_path):
    """When no session exists for today, prompt the user to create one."""
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    out = run_hook(sessions_root)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "Create session directory" in ctx


def test_session_md_only_injects_discover(tmp_path):
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    make_session(sessions_root, "slug", ["SESSION.md"])
    out = run_hook(sessions_root)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "Discover" in ctx


def test_discovery_present_injects_plan(tmp_path):
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    make_session(sessions_root, "slug", ["SESSION.md", "DISCOVERY.md"])
    out = run_hook(sessions_root)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "Plan" in ctx


def test_plan_present_injects_implement(tmp_path):
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    make_session(
        sessions_root, "slug", ["SESSION.md", "DISCOVERY.md", "PLAN.md"]
    )
    out = run_hook(sessions_root)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "Implement" in ctx


def test_no_sessions_root_is_safe(tmp_path):
    """Hook should not crash when the sessions root itself doesn't exist."""
    sessions_root = tmp_path / "nonexistent"
    out = run_hook(sessions_root)
    # Should emit the "create session directory" reminder, not crash.
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "Create session directory" in ctx
