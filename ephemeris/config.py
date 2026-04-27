"""config.py — load and apply ephemeris configuration.

Configuration is JSON to keep the plugin stdlib-only. Default config is
universal — every Claude Code user has `~/.claude/projects/`. Doc-tree and
arbitrary-markdown sources are opt-in.

Default config (bootstrapped on first run if absent):

    {
      "version": 1,
      "wiki_root": "~/.claude/ephemeris/wiki",
      "cursor_path": "~/.claude/ephemeris/cursor.json",
      "sources": [
        {
          "id": "native-claude-projects",
          "kind": "native-transcript",
          "root": "~/.claude/projects/",
          "scope": {
            "exclude": ["~/.claude/**", "**/ephemeris/**"]
          },
          "filter_title_gen": true
        }
      ]
    }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ephemeris.scope import ScopeConfig
from ephemeris.sources.arbitrary_md import ArbitraryMarkdownSource
from ephemeris.sources.base import Source
from ephemeris.sources.native_transcript import NativeTranscriptSource
from ephemeris.sources.session_docs import SectionExtractor, SessionDocsSource

CONFIG_VERSION = 1
DEFAULT_CONFIG_PATH = Path("~/.claude/ephemeris/config.json").expanduser()
DEFAULT_WIKI_ROOT = Path("~/.claude/ephemeris/wiki").expanduser()
DEFAULT_CURSOR_PATH = Path("~/.claude/ephemeris/cursor.json").expanduser()

DEFAULT_CONFIG: dict[str, object] = {
    "version": CONFIG_VERSION,
    "wiki_root": "~/.claude/ephemeris/wiki",
    "cursor_path": "~/.claude/ephemeris/cursor.json",
    "sources": [
        {
            "id": "native-claude-projects",
            "kind": "native-transcript",
            "root": "~/.claude/projects/",
            "scope": {
                "exclude": ["~/.claude/**", "**/ephemeris/**"],
            },
            "filter_title_gen": True,
        }
    ],
}


@dataclass
class SourceSpec:
    """Resolved configuration for a single source.

    Held alongside the constructed Source object so the engine can correlate
    cursor entries to user-friendly source IDs.
    """

    id: str
    kind: str
    root: Path
    source: Source


@dataclass
class EphemerisConfig:
    """Resolved ephemeris configuration."""

    wiki_root: Path = field(default_factory=lambda: DEFAULT_WIKI_ROOT)
    cursor_path: Path = field(default_factory=lambda: DEFAULT_CURSOR_PATH)
    sources: list[SourceSpec] = field(default_factory=list)


def load_config(path: Path | None = None) -> EphemerisConfig:
    """Load ephemeris config from disk, bootstrapping the default if absent.

    Args:
        path: Override path. Defaults to `~/.claude/ephemeris/config.json`.

    Returns:
        Parsed EphemerisConfig with constructed Source objects.

    Never raises on missing-file or malformed-JSON — falls back to default.
    """
    cfg_path = path if path is not None else DEFAULT_CONFIG_PATH
    raw: dict[str, object]
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = dict(DEFAULT_CONFIG)
    else:
        raw = dict(DEFAULT_CONFIG)
        # Best-effort bootstrap; ignore failures.
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    return _build_config(raw)


def _build_config(raw: dict[str, object]) -> EphemerisConfig:
    wiki_root = Path(str(raw.get("wiki_root", DEFAULT_WIKI_ROOT))).expanduser()
    cursor_path = Path(str(raw.get("cursor_path", DEFAULT_CURSOR_PATH))).expanduser()
    sources_raw = raw.get("sources", [])
    sources: list[SourceSpec] = []
    if isinstance(sources_raw, list):
        for entry in sources_raw:
            if not isinstance(entry, dict):
                continue
            spec = _build_source_spec(entry)
            if spec is not None:
                sources.append(spec)
    return EphemerisConfig(wiki_root=wiki_root, cursor_path=cursor_path, sources=sources)


def _build_source_spec(entry: dict[str, object]) -> SourceSpec | None:
    sid = entry.get("id")
    kind = entry.get("kind")
    root_raw = entry.get("root", "")
    if not isinstance(sid, str) or not isinstance(kind, str):
        return None
    if not isinstance(root_raw, str):
        return None
    root = Path(root_raw).expanduser()

    if kind == "native-transcript":
        scope_obj = entry.get("scope", {}) if isinstance(entry.get("scope"), dict) else {}
        include = scope_obj.get("include", []) if isinstance(scope_obj, dict) else []
        exclude = scope_obj.get("exclude", []) if isinstance(scope_obj, dict) else []
        scope = ScopeConfig(
            include=list(include) if isinstance(include, list) else [],
            exclude=list(exclude) if isinstance(exclude, list) else [],
        )
        filter_title_gen = bool(entry.get("filter_title_gen", True))
        source = NativeTranscriptSource(
            scope=scope,
            filter_title_gen=filter_title_gen,
        )
    elif kind == "session-docs":
        dir_pattern_str = entry.get("dir_pattern")
        dir_pattern = None
        if isinstance(dir_pattern_str, str) and dir_pattern_str:
            try:
                dir_pattern = re.compile(dir_pattern_str)
            except re.error:
                dir_pattern = None
        extractors_raw = entry.get("extractors", {})
        extractors: dict[str, SectionExtractor] = {}
        if isinstance(extractors_raw, dict):
            for fname, spec in extractors_raw.items():
                if not isinstance(fname, str) or not isinstance(spec, dict):
                    continue
                sections_raw = spec.get("sections", [])
                if isinstance(sections_raw, list):
                    extractors[fname] = SectionExtractor(
                        sections=[s for s in sections_raw if isinstance(s, str)]
                    )
        source = SessionDocsSource(dir_pattern=dir_pattern, extractors=extractors)
    elif kind == "arbitrary-md":
        source = ArbitraryMarkdownSource()
    else:
        return None

    return SourceSpec(id=sid, kind=kind, root=root, source=source)
