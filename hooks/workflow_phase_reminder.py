#!/usr/bin/env python3
"""UserPromptSubmit hook — injects brief phase-specific reminder.

Detects which QRSPI workflow phase the user is in by inspecting today's
session directory under ~/src/.ai/sessions/ and emits a short reminder via
the UserPromptSubmit additionalContext mechanism.

Phase detection (conservative — only inject when exactly one phase matches):
    no session dir         -> "Create session directory"
    SESSION.md only        -> Discover
    DISCOVERY.md present   -> Plan
    PLAN.md present        -> Implement

Stdlib only (json, os, pathlib, sys, datetime). No extra deps.

Environment:
    EPHEMERIS_SESSIONS_ROOT  override default ~/src/.ai/sessions (used in tests)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

DEFAULT_SESSIONS_ROOT = Path.home() / "src" / ".ai" / "sessions"

REMINDERS = {
    "none": (
        "No session directory exists for today. "
        "Create session directory ~/src/.ai/sessions/YYYY-MM-DD_<TICKET>_<SLUG>/ "
        "before continuing (see docs/workflow-phases.md)."
    ),
    "discover": (
        "Phase: Discover — read code, answer the question list, "
        "capture findings in DISCOVERY.md with file:line evidence."
    ),
    "plan": (
        "Phase: Plan — create PLAN.md with ordered steps, risks, "
        "verification, and git strategy. Wait for explicit approval before implementing."
    ),
    "implement": (
        "Phase: Implement — execute one step at a time, RED-GREEN-REFACTOR "
        "for behavioral changes, update SESSION.md as you go."
    ),
}


def sessions_root() -> Path:
    override = os.environ.get("EPHEMERIS_SESSIONS_ROOT")
    if override:
        return Path(override)
    return DEFAULT_SESSIONS_ROOT


def todays_session(root: Path) -> Path | None:
    """Return the session directory for today, if exactly one exists."""
    if not root.exists():
        return None
    prefix = date.today().isoformat()
    matches = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)]
    if len(matches) != 1:
        return None
    return matches[0]


def detect_phase(session_dir: Path | None) -> str:
    if session_dir is None:
        return "none"
    if (session_dir / "PLAN.md").exists():
        return "implement"
    if (session_dir / "DISCOVERY.md").exists():
        return "plan"
    if (session_dir / "SESSION.md").exists():
        return "discover"
    return "none"


def emit(phase: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": REMINDERS[phase],
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main() -> int:
    try:
        # Consume stdin (hook input JSON) — we do not use it, but we must not block.
        _ = sys.stdin.read()
    except Exception:
        pass
    root = sessions_root()
    session = todays_session(root)
    phase = detect_phase(session)
    emit(phase)
    return 0


if __name__ == "__main__":
    sys.exit(main())
