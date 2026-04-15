#!/usr/bin/env python3
"""post_session.py — ephemeris SessionEnd hook stub.

Fires on: SessionEnd (session ends, clear, resume, logout, etc.)
Reads the JSON payload from stdin and exits 0. No ingestion logic yet.
Ingestion logic lands in SPEC-002/SPEC-003.
"""

import json
import sys
from pathlib import Path

# Ensure the hooks package root is on sys.path so _lib is importable
# whether this script is invoked directly or via ${CLAUDE_PLUGIN_ROOT}.
sys.path.insert(0, str(Path(__file__).parent))

from _lib.payload import read_payload  # noqa: E402


def main() -> None:
    payload = read_payload()

    # stub: ingestion logic not yet implemented
    _ = payload
    print(json.dumps({}))


if __name__ == "__main__":
    main()
