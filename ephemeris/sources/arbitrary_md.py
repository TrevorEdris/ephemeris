"""sources/arbitrary_md.py — single-file or single-dir markdown reader.

Used when `/ephemeris:ingest <path>` targets either:
  - a single `.md` file, or
  - a directory that does not match a configured session-docs root.

The unit identifier is the filename stem (file) or directory name (dir);
the date is derived from mtime; structured sections are not extracted (the
model receives raw text only). This is the catch-all path-driven source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ephemeris.sources.base import IngestUnit, Locator

_MAX_TEXT_BYTES = 600_000


@dataclass
class ArbitraryMarkdownSource:
    """Catch-all markdown source. Treats `<root>` as a single ingest unit."""

    max_bytes: int = _MAX_TEXT_BYTES
    kind: str = field(default="arbitrary-md", init=False)

    def scan(self, root: Path) -> Iterable[Locator]:
        """Yield exactly one Locator for `root` if it contains any markdown."""
        if not root.exists():
            return
        if root.is_file() and root.suffix.lower() == ".md":
            yield self._locator_for(root)
            return
        if root.is_dir():
            if not any(root.glob("*.md")):
                return
            yield self._locator_for(root)

    def read(self, locator: Locator) -> IngestUnit:
        chunks: list[str] = []
        latest_mtime = 0.0
        total = 0

        if locator.path.is_file():
            md_files = [locator.path]
        else:
            md_files = sorted(locator.path.glob("*.md"))

        for md in md_files:
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
                mtime = md.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
            chunk = f"=== {md.name} ===\n{text}\n"
            cb = chunk.encode("utf-8")
            if total + len(cb) > self.max_bytes:
                remaining = self.max_bytes - total
                if remaining > 0:
                    chunks.append(cb[:remaining].decode("utf-8", errors="ignore"))
                break
            chunks.append(chunk)
            total += len(cb)

        return IngestUnit(
            locator=locator,
            raw_text="".join(chunks),
            source_mtime=latest_mtime,
        )

    def _locator_for(self, path: Path) -> Locator:
        identifier = path.stem if path.is_file() else path.name
        try:
            ts = path.stat().st_mtime
            when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except OSError:
            when = ""
        return Locator(
            path=path.resolve(),
            kind=self.kind,
            identifier=identifier,
            when=when,
        )
