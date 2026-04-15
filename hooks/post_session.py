#!/usr/bin/env python3
"""post_session.py — ephemeris SessionEnd hook.

Fires on: SessionEnd (session ends, clear, resume, logout, etc.)
Reads the JSON payload from stdin, extracts transcript_path, and persists
the transcript bytes to staging storage via ephemeris.capture.

After a successful capture, spawns ``python -m ephemeris.ingest`` as a
detached background subprocess (start_new_session=True) so wiki ingestion
happens asynchronously without blocking the session close. The hook returns
immediately regardless of the ingestion outcome.

Staging root defaults to ~/.claude/ephemeris/staging but can be overridden
via the EPHEMERIS_STAGING_ROOT environment variable (used by tests).

Environment controls:
    EPHEMERIS_INGEST_ON_CAPTURE  — set to "0" to disable auto-trigger (tests)
    EPHEMERIS_WIKI_ROOT          — wiki root dir (default: ~/.claude/ephemeris/wiki)
    EPHEMERIS_LOG_PATH           — diagnostic log (default: ~/.claude/ephemeris/ephemeris.log)
    EPHEMERIS_MODEL_CLIENT       — 'anthropic' or 'fake' (default: 'anthropic')

Hook failure isolation: if capture raises, the error is printed to stderr
and the hook exits 0 — never disturbing the Claude Code session (SPEC-001 AC-7).
The background ingestion process is similarly isolated; hook does not wait for it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure the hooks package root is on sys.path so _lib is importable
# whether this script is invoked directly or via ${CLAUDE_PLUGIN_ROOT}.
sys.path.insert(0, str(Path(__file__).parent))

# Ensure the repo root is on sys.path so ephemeris package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

from _lib.payload import read_payload  # noqa: E402
from _lib.staging_root import resolve_staging_root  # noqa: E402
from ephemeris.scope import is_in_scope, load_scope_config  # noqa: E402

HOOK_TYPE = "session-end"


def _spawn_ingestion() -> None:
    """Spawn python -m ephemeris.ingest as a detached background subprocess.

    Uses start_new_session=True (POSIX) to put the child in its own process
    group so it survives the parent hook process exiting. stdout and stderr
    are discarded — the child logs to ephemeris.log directly.
    """
    try:
        subprocess.Popen(
            [sys.executable, "-m", "ephemeris.ingest"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        # Log but never raise — hook isolation must be preserved
        print(
            f"ephemeris: failed to spawn background ingestion: {exc}",
            file=sys.stderr,
        )


def main() -> None:
    payload = read_payload()

    # Scope check — runs immediately after payload parse, before any capture.
    # Reads scope.json on every invocation (hot-reload guarantee — AC-4).
    # Falls back to all-capture if config is absent or invalid (AC-1, AC-5).
    scope = load_scope_config()
    cwd = payload.get("cwd", "") if isinstance(payload, dict) else ""
    if not is_in_scope(cwd, scope):
        # Silent skip — no error surfaced to user (SPEC-007 AC-6).
        print(json.dumps({"status": "skipped", "reason": "out_of_scope"}))
        return

    staging_root = resolve_staging_root()
    if staging_root is None:
        # EPHEMERIS_STAGING_ROOT is set to an invalid value (empty or relative).
        # Log to stderr and exit 0 to maintain hook isolation — never disturb
        # the Claude Code session.
        print(
            "ephemeris: EPHEMERIS_STAGING_ROOT must be absolute (or unset). "
            "Skipping capture.",
            file=sys.stderr,
        )
        print(json.dumps({}))
        return

    try:
        from ephemeris.capture import capture
        from ephemeris.exceptions import CaptureError

        try:
            result_path = capture(
                hook_type=HOOK_TYPE,
                payload=payload,
                staging_root=staging_root,
            )
            print(json.dumps({"ok": True, "path": str(result_path)}))

            # Spawn background ingestion unless explicitly disabled (e.g., tests)
            ingest_on_capture = os.environ.get("EPHEMERIS_INGEST_ON_CAPTURE", "1")
            if ingest_on_capture != "0":
                _spawn_ingestion()

        except CaptureError:
            # Expected errors (missing transcript, invalid payload, etc.) are
            # a silent no-op — the hook fires but there is nothing to capture.
            print(json.dumps({}))
    except Exception as exc:
        # Unexpected errors (import failure, etc.) are logged to stderr.
        print(f"ephemeris unexpected error ({HOOK_TYPE}): {exc}", file=sys.stderr)
        print(json.dumps({}))


if __name__ == "__main__":
    main()
