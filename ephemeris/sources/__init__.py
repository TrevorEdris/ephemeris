"""sources — pluggable readers that produce IngestUnits for the ingest engine.

Each source knows how to enumerate locators under a root and how to read a
single locator into a uniform `IngestUnit`. The ingest engine consumes
IngestUnits and is source-agnostic.
"""

from ephemeris.sources.base import IngestUnit, Locator, Source
from ephemeris.sources.native_transcript import NativeTranscriptSource
from ephemeris.sources.session_docs import SessionDocsSource
from ephemeris.sources.arbitrary_md import ArbitraryMarkdownSource

__all__ = [
    "IngestUnit",
    "Locator",
    "Source",
    "NativeTranscriptSource",
    "SessionDocsSource",
    "ArbitraryMarkdownSource",
]
