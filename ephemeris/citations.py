"""citations.py — citation key generation and dedup helpers.

Wiki pages end with a `## Sessions` block containing one citation per
contributing source. Citation format is:

    > Source: [YYYY-MM-DD <kind>:<id-or-slug>]

Old format `> Source: [YYYY-MM-DD <id>]` (without kind prefix) is still
recognized for backwards-compatibility — `is_cited` matches both shapes.
"""

from __future__ import annotations

import re

CITATION_PREFIX = "> Source: "

# Match either:
#   [YYYY-MM-DD kind:id]
#   [YYYY-MM-DD id]
_CITATION_RE = re.compile(
    r"^>\s*Source:\s*\[(\d{4}-\d{2}-\d{2})\s+(?:([a-z][a-z0-9_-]*):)?([^\]]+)\]\s*$",
    re.MULTILINE,
)


def format_citation(when: str, kind: str, identifier: str) -> str:
    """Build a citation line in the new kind-prefixed format."""
    return f"{CITATION_PREFIX}[{when} {kind}:{identifier}]"


def is_cited(page_text: str, when: str, kind: str, identifier: str) -> bool:
    """Return True when this exact (when, kind, identifier) is already cited.

    Matches both the new `[date kind:id]` and old `[date id]` formats so a
    re-ingest after a schema bump doesn't double-cite.
    """
    target_id = identifier.strip()
    target_when = when.strip()
    target_kind = kind.strip()
    for match in _CITATION_RE.finditer(page_text):
        m_when, m_kind, m_id = match.group(1), match.group(2), match.group(3).strip()
        if m_when != target_when:
            continue
        if m_id != target_id:
            continue
        if m_kind is None:
            # Old format: id-only match counts as cited regardless of kind.
            return True
        if m_kind == target_kind:
            return True
    return False


def append_citation(page_text: str, when: str, kind: str, identifier: str) -> str:
    """Append a citation line if not already present.

    The page text is returned unchanged when the citation is already present
    (under either old or new format). When appending, ensures a trailing
    newline so the file ends cleanly.
    """
    if is_cited(page_text, when, kind, identifier):
        return page_text
    line = format_citation(when, kind, identifier)
    if not page_text.endswith("\n"):
        page_text += "\n"
    return page_text + line + "\n"
