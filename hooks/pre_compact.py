#!/usr/bin/env python3
"""pre_compact.py — ephemeris PreCompact hook.

Fires on: PreCompact (before context compaction)
Reads the JSON payload from stdin, extracts transcript_path, and persists
the transcript bytes to staging storage via ephemeris.capture.

Staging root defaults to ~/.claude/ephemeris/staging but can be overridden
via the EPHEMERIS_STAGING_ROOT environment variable (used by tests).

Hook failure isolation: if capture raises, the error is printed to stderr
and the hook exits 0 — never disturbing the Claude Code session (SPEC-001 AC-7).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure the hooks package root is on sys.path so _lib is importable
# whether this script is invoked directly or via ${CLAUDE_PLUGIN_ROOT}.
sys.path.insert(0, str(Path(__file__).parent))

# Ensure the repo root is on sys.path so ephemeris package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

from _lib.payload import read_payload  # noqa: E402

HOOK_TYPE = "pre-compact"
DEFAULT_STAGING_ROOT = Path.home() / ".claude" / "ephemeris" / "staging"


def main() -> None:
    payload = read_payload()

    staging_root = Path(
        os.environ.get("EPHEMERIS_STAGING_ROOT", str(DEFAULT_STAGING_ROOT))
    )

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
