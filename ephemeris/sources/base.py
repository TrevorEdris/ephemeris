"""sources/base.py — Source protocol and the IngestUnit produced by sources.

A `Source` enumerates `Locator`s under a root and reads each into an
`IngestUnit`. The IngestUnit is the uniform handoff to the ingest engine —
the engine never inspects source-specific fields.

Public API:
    Locator       — opaque pointer to a single ingestible unit (file, dir, etc.)
    IngestUnit    — the dataclass produced by Source.read
    Source        — Protocol describing the source contract

Source implementations live in sibling modules. New source kinds are added by
implementing this Protocol and registering in `ephemeris.sources.__init__`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable


@dataclass(frozen=True)
class Locator:
    """Opaque pointer to a single ingestible unit.

    Attributes:
        path:        Filesystem path, dir or file. Always absolute.
        kind:        Source kind tag (e.g. "native-transcript", "session-docs").
        identifier:  Stable identifier for citation. For transcripts, the session
                     UUID. For doc-tree dirs, the slug.
        when:        Date string in YYYY-MM-DD form for citation. Falls back to
                     mtime-derived date if no inherent date is present.
    """

    path: Path
    kind: str
    identifier: str
    when: str


@dataclass
class IngestUnit:
    """Uniform handoff from a Source to the ingest engine.

    Attributes:
        locator:             Locator that produced this unit.
        raw_text:            Free-form text content the model can reason over.
                             For transcripts: the role-prefixed message log.
                             For docs: a structured dump of the directory.
        structured_sections: Optional pre-extracted named sections. Keyed by a
                             user-supplied section name (e.g. "findings",
                             "decisions"). Empty dict when no patterns matched.
        metadata:            Free-form metadata bag (references, tags, etc.).
        source_mtime:        Latest mtime across files contributing to this unit.
                             Used by the cursor for incremental re-runs.
    """

    locator: Locator
    raw_text: str
    structured_sections: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
    source_mtime: float = 0.0


@runtime_checkable
class Source(Protocol):
    """Source protocol — pluggable reader for ingest content.

    Implementations are not required to subclass; structural typing via
    `Protocol` is sufficient. The two required operations are `scan` and
    `read`.
    """

    kind: str  # source kind tag

    def scan(self, root: Path) -> Iterable[Locator]:
        """Yield every locator under `root` that this source can handle.

        Order is not specified. Callers that need stable ordering should sort
        by locator.identifier or .when.
        """
        ...

    def read(self, locator: Locator) -> IngestUnit:
        """Read a single locator into an IngestUnit.

        Must not write to disk. Raises if the locator is unreadable.
        """
        ...
