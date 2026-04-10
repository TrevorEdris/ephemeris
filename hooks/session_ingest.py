#!/usr/bin/env python3
"""UserPromptSubmit hook — auto-prompts ingest of the most recent past session.

Closes the loop on the ingest workflow without manual ``/ingest`` invocations.
When the user starts a new prompt:

1. Walk session dirs under ``$EPHEMERIS_SESSIONS_ROOT`` (default
   ``~/src/.ai/sessions``).
2. Select the most recent session dated strictly before today.
3. Skip if the session has no ``DISCOVERY.md`` and no ``PLAN.md``.
4. Skip if the session is already listed in the state file
   ``$EPHEMERIS_STATE_ROOT/ingested-sessions.json``
   (default ``~/.ai/ephemeris/state/ingested-sessions.json``).
5. Otherwise emit an ``additionalContext`` payload instructing the LLM to
   run ``python $CLAUDE_PLUGIN_ROOT/scripts/ingest/ingest_sessions.py <path>``.

Stdlib only (``json``, ``os``, ``pathlib``, ``sys``, ``datetime``, ``re``).
The hook never calls Graphiti itself — that's the ingest script's job.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

DEFAULT_SESSIONS_ROOT = Path.home() / "src" / ".ai" / "sessions"
DEFAULT_STATE_ROOT = Path.home() / ".ai" / "ephemeris" / "state"
STATE_FILENAME = "ingested-sessions.json"

SESSION_DIR_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?:[A-Z]+-\d+_)?.+$"
)


def sessions_root() -> Path:
    override = os.environ.get("EPHEMERIS_SESSIONS_ROOT")
    return Path(override) if override else DEFAULT_SESSIONS_ROOT


def state_root() -> Path:
    override = os.environ.get("EPHEMERIS_STATE_ROOT")
    return Path(override) if override else DEFAULT_STATE_ROOT


def load_ingested(state_dir: Path) -> set[str]:
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / STATE_FILENAME
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text())
        if isinstance(data, list):
            return {str(x) for x in data}
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def most_recent_past_session(root: Path) -> Path | None:
    """Return the newest session dir with a date strictly before today."""
    if not root.exists():
        return None
    today = date.today().isoformat()
    candidates: list[Path] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        m = SESSION_DIR_RE.match(p.name)
        if not m:
            continue
        if m.group("date") >= today:
            continue
        candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def is_ingestable(path: Path) -> bool:
    return (path / "DISCOVERY.md").exists() or (path / "PLAN.md").exists()


def build_instruction(path: Path) -> str:
    return (
        f"Previous session `{path.name}` has not been ingested yet. "
        f"Run: python3 ${{CLAUDE_PLUGIN_ROOT}}/scripts/ingest/ingest_sessions.py "
        f"{path} --dry-run  (preview), then rerun without --dry-run to commit. "
        f"This pulls Decisions / Problems / TechChoices from DISCOVERY.md and PLAN.md "
        f"into the workflow-knowledge graph so future /query calls can surface them."
    )


def emit(context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main() -> int:
    try:
        _ = sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass

    state_dir = state_root()
    ingested = load_ingested(state_dir)

    session = most_recent_past_session(sessions_root())
    if session is None or not is_ingestable(session) or session.name in ingested:
        emit("")
        return 0

    emit(build_instruction(session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
