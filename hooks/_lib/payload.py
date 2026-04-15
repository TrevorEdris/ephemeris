"""payload.py — shared stdin read-and-parse helper for ephemeris hooks.

Provides a single entry point for reading the Claude Code hook JSON payload
from stdin. Handles empty input and malformed JSON defensively, always
returning a dict so callers need not guard against None or exceptions.
"""

import json
import sys


def read_payload() -> dict:
    """Read and parse the JSON payload from stdin.

    Returns a parsed dict on success. Returns an empty dict if stdin is
    empty or contains non-JSON data — defensive fallback so hook stubs
    never crash due to missing or malformed input.
    """
    stdin_data = sys.stdin.read()
    try:
        return json.loads(stdin_data)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {}
