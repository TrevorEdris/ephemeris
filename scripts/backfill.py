#!/usr/bin/env python3
"""scripts/backfill.py — one-time replay tool for ephemeris v0.2.0+.

Walks every source declared in `~/.claude/ephemeris/config.json` (or a
config path supplied via ``--config``) and prints the locators that would
be ingested. Use ``--with-cursor-init`` to seed the cursor with current
mtimes (so subsequent ``/ephemeris:ingest`` runs are no-ops on already-seen
content).

Optional ``--legacy-staging`` mode walks the pre-v0.2.0 hook output dirs
(`~/.claude/ephemeris/staging/{session-end,pre-compact,processed,pending}/`)
so users upgrading from v0.1.x can mop up backlog.

This script does not perform model reasoning — actual ingestion still
happens via ``/ephemeris:ingest``. Backfill exists to enumerate work and
optionally seed the cursor.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ephemeris.config import load_config
from ephemeris.cursor import Cursor
from ephemeris.sources.native_transcript import NativeTranscriptSource

LEGACY_STAGING_DIRS = [
    Path("~/.claude/ephemeris/staging/session-end").expanduser(),
    Path("~/.claude/ephemeris/staging/pre-compact").expanduser(),
    Path("~/.claude/ephemeris/staging/processed").expanduser(),
    Path("~/.claude/ephemeris/staging/pending").expanduser(),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=lambda s: Path(s).expanduser())
    parser.add_argument("--with-cursor-init", action="store_true")
    parser.add_argument("--legacy-staging", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    cursor = Cursor.load(config.cursor_path)
    seen = 0

    for spec in config.sources:
        for locator in spec.source.scan(spec.root):
            try:
                mtime = locator.path.stat().st_mtime
            except OSError:
                mtime = 0.0
            sys.stdout.write(
                f"{spec.id}\t{locator.kind}\t{locator.identifier}\t"
                f"{locator.when}\t{locator.path}\n"
            )
            seen += 1
            if args.with_cursor_init:
                cursor.update(spec.id, locator, mtime, run_id="backfill")

    if args.legacy_staging:
        legacy = NativeTranscriptSource(filter_title_gen=False)
        for staging_dir in LEGACY_STAGING_DIRS:
            if not staging_dir.exists():
                continue
            for jsonl in sorted(staging_dir.glob("*.jsonl")):
                # Synthesize a minimal locator using the JSONL stem as id.
                from ephemeris.sources.base import Locator
                from datetime import datetime, timezone
                try:
                    ts = jsonl.stat().st_mtime
                except OSError:
                    ts = 0.0
                when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                locator = Locator(
                    path=jsonl,
                    kind="native-transcript",
                    identifier=jsonl.stem,
                    when=when,
                )
                sys.stdout.write(
                    f"legacy-staging\tnative-transcript\t{locator.identifier}\t"
                    f"{locator.when}\t{locator.path}\n"
                )
                seen += 1
                if args.with_cursor_init:
                    cursor.update("legacy-staging", locator, ts, run_id="backfill")

    if args.with_cursor_init:
        cursor.save()
        sys.stderr.write(f"# cursor seeded with {seen} entries at {config.cursor_path}\n")

    sys.stderr.write(f"# total: {seen} locators\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
