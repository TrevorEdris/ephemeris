#!/usr/bin/env python3
"""post_session.py — ephemeris SessionEnd hook (deprecated, no-op since v0.2.0).

ephemeris v0.2.0 reads native Claude Code transcripts directly from
``~/.claude/projects/`` rather than copying them through staging. This hook
remains in the plugin manifest for backwards compatibility but performs no
work; ingestion is now driven by `/ephemeris:ingest`.

Hook failure isolation: prints an empty JSON object to stdout and exits 0
so Claude Code session lifecycle is never disturbed.
"""

from __future__ import annotations

import json


def main() -> None:
    # Intentional no-op since v0.2.0. See `/ephemeris:ingest`.
    print(json.dumps({}))


if __name__ == "__main__":
    main()
