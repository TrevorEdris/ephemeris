"""cursor.py — incremental ingest watermarks per source.

The cursor records the last-seen mtime per (source-id, locator-id) so a
subsequent `/ephemeris:ingest` run can short-circuit unchanged inputs.

File format (`~/.claude/ephemeris/cursor.json` by default):

    {
      "version": 1,
      "sources": {
        "<source-id>": {
          "<locator-id>": {
            "last_seen_mtime": 1714137600.0,
            "last_run_id": "abc123def456"
          }
        }
      }
    }

Atomic writes (tempfile + os.replace) keep the cursor consistent on crash.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ephemeris.sources.base import Locator

CURSOR_VERSION = 1


@dataclass
class Cursor:
    """In-memory cursor state.

    Attributes:
        path:    File path the cursor is loaded from / saved to.
        version: Schema version. Currently 1.
        sources: Map of source-id → (locator-id → entry dict).
    """

    path: Path
    version: int = CURSOR_VERSION
    sources: dict[str, dict[str, dict[str, object]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Cursor":
        """Load a cursor file. Missing or malformed file → empty cursor."""
        cursor = cls(path=path)
        if not path.exists():
            return cursor
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cursor
        if not isinstance(data, dict):
            return cursor
        version = data.get("version", 1)
        if not isinstance(version, int):
            version = 1
        cursor.version = version
        sources = data.get("sources", {})
        if isinstance(sources, dict):
            for sid, entries in sources.items():
                if isinstance(sid, str) and isinstance(entries, dict):
                    cursor.sources[sid] = {
                        lid: e for lid, e in entries.items()
                        if isinstance(lid, str) and isinstance(e, dict)
                    }
        return cursor

    def is_fresh(self, source_id: str, locator: Locator, source_mtime: float) -> bool:
        """Return True when the cursor already covers this locator at this mtime."""
        entry = self.sources.get(source_id, {}).get(locator.identifier)
        if not isinstance(entry, dict):
            return False
        last = entry.get("last_seen_mtime")
        if not isinstance(last, (int, float)):
            return False
        return float(last) >= source_mtime

    def update(
        self,
        source_id: str,
        locator: Locator,
        source_mtime: float,
        run_id: str,
    ) -> None:
        """Record a successful ingest of (source_id, locator)."""
        self.sources.setdefault(source_id, {})[locator.identifier] = {
            "last_seen_mtime": float(source_mtime),
            "last_run_id": run_id,
        }

    def save(self) -> None:
        """Atomically persist the cursor to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "sources": self.sources,
        }
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        fd, tmp_path = tempfile.mkstemp(
            prefix=".cursor-",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
