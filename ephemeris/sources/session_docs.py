"""sources/session_docs.py — read user-managed session-doc trees.

A session-doc tree is a directory of session subdirectories. Each
subdirectory contains one or more Markdown files documenting a single work
session — typically `SESSION.md`, `DISCOVERY.md`, `PLAN.md`, but the schema
is open. This source supports any markdown set the user maintains.

Public API:
    SessionDocsSource

Behavior:
    - Plugin ships **no built-in heading patterns**. The user supplies
      `dir_pattern` (regex) and `extractors` (filename → section list) via
      configuration. If neither is supplied, the source still works in
      pass-through mode: every direct subdirectory becomes a Locator and the
      whole concatenated markdown becomes `raw_text`.
    - Hybrid extraction (option C): when `extractors` declares headings for a
      filename, those sections are pulled into `structured_sections` AND the
      raw text is included for the model to read.
    - Date is derived from a `dir_pattern` capture group when present, else
      from directory mtime.
    - Obsidian wikilinks `[[target]]` are extracted into `metadata.references`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ephemeris.sources.base import IngestUnit, Locator

# Maximum bytes of concatenated markdown to include in raw_text.
_MAX_TEXT_BYTES = 600_000

_WIKILINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")


@dataclass
class SectionExtractor:
    """Per-filename heading extractor.

    Attributes:
        sections: Heading text strings to look for. Matched as `## <section>`
                  or `### <section>` case-insensitively. Heading match
                  inclusive of trailing `:` and optional level prefix.
    """

    sections: list[str] = field(default_factory=list)


@dataclass
class SessionDocsSource:
    """Source reader for `<root>/<session-dir>/*.md` trees.

    Attributes:
        dir_pattern:        Regex applied to subdirectory names. When the
                            pattern has at least one capture group, the first
                            group is parsed as YYYY-MM-DD for citation date.
                            When None, every direct subdirectory is a candidate
                            and date falls back to mtime.
        extractors:         Map of filename → SectionExtractor.
                            Default empty: pass-through mode.
        max_bytes:          Cap on `raw_text` size (bytes). Default 600KB.
        kind:               Source kind tag — always "session-docs".
    """

    dir_pattern: re.Pattern[str] | None = None
    extractors: dict[str, SectionExtractor] = field(default_factory=dict)
    max_bytes: int = _MAX_TEXT_BYTES
    kind: str = field(default="session-docs", init=False)

    def scan(self, root: Path) -> Iterable[Locator]:
        """Yield Locators for each candidate subdirectory under ``root``."""
        if not root.exists() or not root.is_dir():
            return
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            slug, when = self._slug_and_date(entry)
            if slug is None:
                continue
            # Skip dirs with no markdown.
            if not any(entry.glob("*.md")):
                continue
            yield Locator(
                path=entry,
                kind=self.kind,
                identifier=slug,
                when=when,
            )

    def read(self, locator: Locator) -> IngestUnit:
        """Read every markdown file under the locator dir into one IngestUnit."""
        sections: dict[str, str] = {}
        references: list[str] = []
        chunks: list[str] = []
        latest_mtime = 0.0
        total_bytes = 0
        truncated = False

        for md_path in sorted(locator.path.glob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8", errors="replace")
                mtime = md_path.stat().st_mtime
            except OSError:
                continue

            if mtime > latest_mtime:
                latest_mtime = mtime

            references.extend(_extract_wikilinks(text))

            extractor = self.extractors.get(md_path.name)
            if extractor is not None:
                for sec_name in extractor.sections:
                    body = _extract_section(text, sec_name)
                    if body is not None:
                        key = f"{md_path.name}:{sec_name}"
                        sections[key] = body

            chunk = f"=== {md_path.name} ===\n{text}\n"
            chunk_bytes = chunk.encode("utf-8")
            if total_bytes + len(chunk_bytes) > self.max_bytes:
                remaining = self.max_bytes - total_bytes
                if remaining > 0:
                    chunks.append(chunk_bytes[:remaining].decode("utf-8", errors="ignore"))
                    total_bytes = self.max_bytes
                truncated = True
                break
            chunks.append(chunk)
            total_bytes += len(chunk_bytes)

        raw_text = "".join(chunks)
        if truncated:
            raw_text += "\n\n[SESSION-DOCS TRUNCATED]"

        metadata: dict[str, object] = {}
        if references:
            metadata["references"] = sorted(set(references))

        return IngestUnit(
            locator=locator,
            raw_text=raw_text,
            structured_sections=sections,
            metadata=metadata,
            source_mtime=latest_mtime,
        )

    def _slug_and_date(self, entry: Path) -> tuple[str | None, str]:
        """Compute (slug, when) for a directory candidate.

        Returns (None, "") if the directory should be skipped.
        """
        if self.dir_pattern is None:
            slug = entry.name
            return slug, _mtime_date(entry)

        m = self.dir_pattern.match(entry.name)
        if not m:
            return None, ""

        # Prefer first capture group as date if it parses.
        when = ""
        if m.groups():
            first = m.group(1)
            try:
                datetime.strptime(first, "%Y-%m-%d")
                when = first
            except ValueError:
                pass
        if not when:
            when = _mtime_date(entry)

        # Slug is the second capture group when present, else the dir name.
        if len(m.groups()) >= 2 and m.group(2):
            slug = m.group(2)
        else:
            slug = entry.name
        return slug, when


def _mtime_date(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _extract_wikilinks(text: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _extract_section(text: str, heading: str) -> str | None:
    """Return the body of `## <heading>` (or `### <heading>`) up to the next heading.

    Case-insensitive heading match. Trailing colon tolerated. Returns None
    when not found.
    """
    pattern = re.compile(
        r"^#{2,3}\s+" + re.escape(heading.strip()) + r":?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return None
    start = m.end()
    next_heading = re.compile(r"^#{1,3}\s+\S", re.MULTILINE)
    nm = next_heading.search(text, pos=start)
    end = nm.start() if nm else len(text)
    return text[start:end].strip()
