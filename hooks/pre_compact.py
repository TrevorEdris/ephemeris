#!/usr/bin/env python3
"""pre_compact.py — ephemeris PreCompact hook stub.

Fires on: PreCompact (before context compaction)
Reads the JSON payload from stdin and exits 0. No ingestion logic yet.
Ingestion logic lands in SPEC-002/SPEC-003.
"""

import json
import sys


def main() -> None:
    stdin_data = sys.stdin.read()
    try:
        payload: dict = json.loads(stdin_data)
    except (json.JSONDecodeError, TypeError):
        payload = {}

    # stub: ingestion logic not yet implemented
    _ = payload
    print(json.dumps({}))


if __name__ == "__main__":
    main()
