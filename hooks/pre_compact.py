#!/usr/bin/env python3
"""pre_compact.py — ephemeris PreCompact hook (deprecated, no-op since v0.2.0).

See post_session.py for context. v0.2.0 sources transcripts from
``~/.claude/projects/`` directly.
"""

from __future__ import annotations

import json


def main() -> None:
    # Intentional no-op since v0.2.0. See `/ephemeris:ingest`.
    print(json.dumps({}))


if __name__ == "__main__":
    main()
