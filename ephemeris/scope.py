"""scope.py — Capture scope configuration for the ephemeris plugin.

Loads an optional JSON config at $EPHEMERIS_SCOPE_CONFIG (defaults to
~/.claude/plugins/ephemeris/scope.json) and provides the is_in_scope
predicate used by the capture hooks to filter sessions.

Public API:
    ScopeConfig  — dataclass with include/exclude pattern lists
    load_scope_config(path) -> ScopeConfig
    is_in_scope(cwd, config) -> bool

Translation note (SPEC-007 deviation):
    The spec references scope.yaml (YAML format). This implementation uses
    scope.json because Python's stdlib has no YAML parser. JSON is stdlib
    and expresses the same schema cleanly. Config path is
    ~/.claude/plugins/ephemeris/scope.json (not scope.yaml).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ephemeris.scope")

_DEFAULT_SCOPE_CONFIG: Path = (
    Path.home() / ".claude" / "plugins" / "ephemeris" / "scope.json"
)


@dataclass
class ScopeConfig:
    """Capture scope configuration.

    Attributes:
        include: List of glob patterns. If non-empty, only sessions whose
            cwd matches at least one pattern are captured.
        exclude: List of glob patterns. Sessions whose cwd matches any
            pattern are always skipped, even if they match an include pattern.
    """

    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


def _normalize_patterns(patterns: list[str]) -> list[str]:
    """Strip whitespace from patterns and filter out empty strings."""
    return [p.strip() for p in patterns if p.strip()]


def load_scope_config(path: Optional[Path] = None) -> ScopeConfig:
    """Load scope configuration from a JSON file.

    Reads the config from ``path`` if supplied, otherwise from the path
    specified by the ``EPHEMERIS_SCOPE_CONFIG`` environment variable, falling
    back to ``~/.claude/plugins/ephemeris/scope.json``.

    Never raises. Returns an empty ScopeConfig (all-capture) if:
    - The file does not exist.
    - The file contains invalid JSON.
    - The JSON has an unexpected schema (include/exclude not lists).
    A WARN-level log is emitted for the last two cases.

    Hot-reload guarantee (AC-4): this function reads the file from disk on
    every call with no caching between invocations. Because each hook
    invocation calls load_scope_config() fresh, any file edit takes effect
    on the next hook invocation automatically — no process restart required.

    Args:
        path: Explicit path to the scope config. Overrides env var and default.

    Returns:
        Parsed ScopeConfig, or empty ScopeConfig on any error.
    """
    if path is None:
        env_path = os.environ.get("EPHEMERIS_SCOPE_CONFIG")
        if env_path:
            candidate = Path(env_path)
            if not candidate.is_absolute():
                logger.warning(
                    "ephemeris.scope: EPHEMERIS_SCOPE_CONFIG must be an absolute path; "
                    "got relative path %r — ignoring and using all-capture default",
                    env_path,
                )
                return ScopeConfig()
            config_path = candidate.expanduser()
        else:
            config_path = _DEFAULT_SCOPE_CONFIG
    else:
        config_path = path

    # Absent file is the zero-config default — no warning needed.
    if not config_path.exists():
        return ScopeConfig()

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "ephemeris.scope: cannot read scope config %s: %s", config_path, exc
        )
        return ScopeConfig()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "ephemeris.scope: invalid JSON in scope config %s: %s", config_path, exc
        )
        return ScopeConfig()

    if not isinstance(data, dict):
        logger.warning(
            "ephemeris.scope: unexpected schema in %s: root must be a JSON object, "
            "got %s",
            config_path,
            type(data).__name__,
        )
        return ScopeConfig()

    include_raw = data.get("include", [])
    exclude_raw = data.get("exclude", [])

    if not isinstance(include_raw, list):
        logger.warning(
            "ephemeris.scope: unexpected schema in %s: 'include' must be a list, "
            "got %s",
            config_path,
            type(include_raw).__name__,
        )
        return ScopeConfig()

    if not isinstance(exclude_raw, list):
        logger.warning(
            "ephemeris.scope: unexpected schema in %s: 'exclude' must be a list, "
            "got %s",
            config_path,
            type(exclude_raw).__name__,
        )
        return ScopeConfig()

    return ScopeConfig(
        include=_normalize_patterns(include_raw),
        exclude=_normalize_patterns(exclude_raw),
    )


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a glob pattern to a full-string regex.

    Glob semantics:
        **   — matches any sequence of characters, including path separators
        *    — matches any sequence of characters EXCEPT a path separator (/)
        ?    — matches exactly one character that is NOT a path separator (/)
        other — treated as literal (regex metacharacters are escaped)

    The resulting regex is anchored at both ends (fullmatch semantics).
    """
    # Split on the special tokens we handle, preserving them via a capture group.
    # Tokens: '**', '*', '?'
    tokens = re.split(r"(\*\*|\*|\?)", pattern)
    regex_parts: list[str] = []
    for token in tokens:
        if token == "**":
            regex_parts.append(".+")  # one or more chars, including /
        elif token == "*":
            regex_parts.append("[^/]*")  # zero or more non-separator chars
        elif token == "?":
            regex_parts.append("[^/]")  # exactly one non-separator char
        else:
            # Escape all regex metacharacters so literals are treated as literals.
            regex_parts.append(re.escape(token))

    return re.compile("^" + "".join(regex_parts) + "$")


def _matches_any(cwd: str, patterns: list[str]) -> bool:
    """Return True if cwd matches at least one glob pattern in patterns."""
    return any(_glob_to_regex(p).fullmatch(cwd) for p in patterns)


def is_in_scope(cwd: str, config: ScopeConfig) -> bool:
    """Determine whether a session's working directory is in capture scope.

    Evaluation logic:
        1. If include is non-empty and cwd does not match any include pattern
           → out of scope (return False).
        2. If cwd matches any exclude pattern → out of scope (return False).
        3. Otherwise → in scope (return True).

    exclude always wins over include.

    Args:
        cwd: The session's working directory path string.
        config: ScopeConfig with include/exclude patterns.

    Returns:
        True if the session should be captured, False if it should be skipped.
    """
    if config.include and not _matches_any(cwd, config.include):
        return False
    if config.exclude and _matches_any(cwd, config.exclude):
        return False
    return True
