"""sources/native_transcript.py — read native Claude Code session transcripts.

Claude Code stores every session transcript at
``~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`` where ``<encoded-cwd>``
is the absolute working directory with ``/`` replaced by ``-``. This source
reads those files directly — no hook-based duplication required.

Public API:
    NativeTranscriptSource

Behavior:
    - `scan(root)` yields a Locator for every ``*.jsonl`` under ``root``,
      walking exactly two directory levels (root → encoded-cwd → file).
    - Optional scope filtering against the decoded cwd path.
    - Optional title-generation sub-session filter (Claude spawns these to
      auto-name conversations; they have one user prompt asking for a title
      and contribute no real content).
    - `read(locator)` reuses the existing JSONL loader and produces an
      IngestUnit with the role-prefixed message text.

The source is independent of the ephemeris hook pipeline. It works on any
machine where Claude Code has stored transcripts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ephemeris.scope import ScopeConfig, is_in_scope
from ephemeris.sources.base import IngestUnit, Locator
from ephemeris.transcript import Message, load_transcript, transcript_to_text

# Heuristic: title-generation sub-sessions match this prompt template anywhere
# inside a JSONL line. Search (not match) is used because the regex is hunting
# inside JSON-encoded content, not at line start.
_TITLE_GEN_PATTERN = re.compile(
    r"Generate a concise \d+(?:[- ]\d+)? word title", re.IGNORECASE
)
_TITLE_GEN_MAX_MESSAGES = 5


@dataclass
class NativeTranscriptSource:
    """Source reader for ``~/.claude/projects/<encoded-cwd>/<id>.jsonl``.

    Attributes:
        scope:               Optional scope config applied to decoded cwd.
        filter_title_gen:    When True, skip auto-naming sub-sessions.
        kind:                Source kind tag — always "native-transcript".
    """

    scope: ScopeConfig | None = None
    filter_title_gen: bool = True
    kind: str = field(default="native-transcript", init=False)

    def scan(self, root: Path) -> Iterable[Locator]:
        """Yield Locators for every JSONL transcript under ``root``.

        Walks exactly the layout Claude Code produces: ``root/<encoded-cwd>/<id>.jsonl``.
        Sub-session and scope filtering happen here so callers don't waste time
        reading transcripts that will be discarded.

        Scope evaluation prefers the authoritative ``cwd`` field embedded in
        the JSONL transcript itself, falling back to a decode of the encoded
        directory name when the JSONL has none.
        """
        if not root.exists() or not root.is_dir():
            return
        for project_dir in sorted(root.iterdir()):
            if not project_dir.is_dir():
                continue
            jsonl_paths = sorted(p for p in project_dir.glob("*.jsonl") if p.is_file())
            if self.scope is not None:
                cwd = _project_cwd(project_dir, jsonl_paths)
                if not is_in_scope(cwd, self.scope):
                    continue
            for jsonl_path in jsonl_paths:
                if self.filter_title_gen and _is_title_gen(jsonl_path):
                    continue
                identifier = jsonl_path.stem
                when = _date_for_path(jsonl_path)
                yield Locator(
                    path=jsonl_path,
                    kind=self.kind,
                    identifier=identifier,
                    when=when,
                )

    def read(self, locator: Locator) -> IngestUnit:
        """Read one transcript file into an IngestUnit."""
        result = load_transcript(locator.path)
        text = transcript_to_text(result.messages)
        try:
            mtime = locator.path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return IngestUnit(
            locator=locator,
            raw_text=text,
            structured_sections={},
            metadata={
                "skipped_lines": result.skipped_lines,
                "message_count": len(result.messages),
            },
            source_mtime=mtime,
        )


def _project_cwd(project_dir: Path, jsonl_paths: list[Path]) -> str:
    """Return the authoritative cwd for a project dir.

    Reads ``cwd`` from the first JSONL that exposes one. Falls back to the
    decoded directory name when no JSONL has the field (best-effort — the
    encoding is lossy).
    """
    for jsonl in jsonl_paths:
        cwd = _peek_cwd(jsonl)
        if cwd:
            return cwd
    return _decode_cwd(project_dir.name)


def _peek_cwd(path: Path) -> str:
    """Return the first ``cwd`` value found in any JSONL record, else "".

    Reads up to the first 32 KB of the file — Claude Code embeds ``cwd`` in
    the user-message records, which appear early. Avoids loading the whole
    transcript when we only need the cwd for scope filtering.
    """
    import json
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            chunk = fh.read(32_000)
    except OSError:
        return ""
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            cwd = obj.get("cwd")
            if isinstance(cwd, str) and cwd:
                return cwd
    return ""


def _decode_cwd(encoded: str) -> str:
    """Reverse Claude Code's encoded-cwd convention: ``-`` → ``/``.

    Best-effort — leading ``-`` becomes leading ``/`` (absolute path); inner
    ``-`` are converted to ``/``. This is the convention observed in
    ``~/.claude/projects/`` and is stable across current Claude Code releases.
    """
    if not encoded:
        return ""
    return "/" + encoded.lstrip("-").replace("-", "/")


def _is_title_gen(path: Path) -> bool:
    """True when a transcript looks like a title-generation sub-session.

    Cheap O(N) scan of the first few lines — Claude Code's title-gen sessions
    have ≤ 5 messages, so we don't need to read the whole file.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, raw in enumerate(fh):
                if line_no >= _TITLE_GEN_MAX_MESSAGES:
                    return False
                if '"type":"user"' not in raw and '"type": "user"' not in raw:
                    continue
                # Look for the title-gen prompt anywhere in the line.
                if _TITLE_GEN_PATTERN.search(raw):
                    return True
        return False
    except OSError:
        return False


def _date_for_path(path: Path) -> str:
    """Return YYYY-MM-DD derived from file mtime (UTC)."""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")
