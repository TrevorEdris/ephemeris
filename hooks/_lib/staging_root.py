"""staging_root.py — resolve EPHEMERIS_STAGING_ROOT env var to a Path.

Public API:
    DEFAULT_STAGING_ROOT: Path — default staging directory (~/.claude/ephemeris/staging)
    resolve_staging_root() -> Path | None

Rules:
- Unset or empty EPHEMERIS_STAGING_ROOT → return DEFAULT_STAGING_ROOT.
- Non-empty value with a leading '~' → expand user home, return result.
- Non-empty absolute path → return as Path.
- Non-empty relative path → return None (caller must reject it).

Returning None signals an invalid configuration. Callers are expected to
print a diagnostic to stderr and exit 0 (hook isolation — never disturb
the Claude Code session).
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_STAGING_ROOT: Path = Path.home() / ".claude" / "ephemeris" / "staging"


def resolve_staging_root() -> Path | None:
    """Resolve EPHEMERIS_STAGING_ROOT to an absolute Path, or None if invalid.

    Returns:
        - DEFAULT_STAGING_ROOT when the env var is unset or empty.
        - An absolute Path when the env var is set to a valid absolute path
          (or a path starting with '~', which is home-expanded).
        - None when the env var is set to a non-empty relative path that
          cannot be resolved safely.
    """
    _env_root = os.environ.get("EPHEMERIS_STAGING_ROOT")
    if _env_root is None:
        # Unset — use the default.
        return DEFAULT_STAGING_ROOT
    if _env_root == "":
        # Explicitly set to empty string — reject to avoid staging to CWD.
        return None

    candidate = Path(_env_root).expanduser()
    if not candidate.is_absolute():
        # Relative paths are rejected to prevent accidental staging to CWD.
        return None

    return candidate
