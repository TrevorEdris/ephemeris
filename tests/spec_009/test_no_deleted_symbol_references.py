"""test_no_deleted_symbol_references.py — SPEC-009 AC-1..AC-7, AC-18, AC-20.

Greps the entire repo (excluding tests/spec_009/ itself and the
.skilmarillion/ specs directory) for references to deleted symbols:

    ephemeris.model, ephemeris.prompts, ephemeris.merge, ephemeris.ingest,
    ephemeris.query, ephemeris.wiki, ephemeris.schema,
    ModelClient, FakeModelClient, DEFAULT_SCHEMA

Asserts zero hits.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

# Directories to exclude from the scan
EXCLUDE_DIRS = {
    REPO_ROOT / "tests" / "spec_009",
    REPO_ROOT / ".skilmarillion",
    REPO_ROOT / ".git",
    REPO_ROOT / "__pycache__",
    # schema/default.md is shipped content (byte-for-byte copy of the prior
    # DEFAULT_SCHEMA constant). It contains example entity names like
    # ModelClient in naming-convention tables — not code imports.
    REPO_ROOT / "schema",
}

# Patterns that must not appear in any file outside the excluded dirs
DELETED_SYMBOLS = [
    r"ephemeris\.model",
    r"ephemeris\.prompts",
    r"ephemeris\.merge",
    r"ephemeris\.ingest",
    r"ephemeris\.query",
    r"ephemeris\.wiki",
    r"ephemeris\.schema",
    r"\bModelClient\b",
    r"\bFakeModelClient\b",
    r"\bDEFAULT_SCHEMA\b",
]

# File extensions to scan
SCAN_EXTENSIONS = {".py", ".md", ".toml", ".json", ".txt"}


def _should_skip(path: Path) -> bool:
    """Return True if path is under any excluded directory."""
    for ex in EXCLUDE_DIRS:
        try:
            path.relative_to(ex)
            return True
        except ValueError:
            pass
    # Skip __pycache__ directories anywhere
    if "__pycache__" in path.parts:
        return True
    return False


def _collect_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if path.is_file() and path.suffix in SCAN_EXTENSIONS and not _should_skip(path):
            files.append(path)
    return files


def test_no_deleted_symbol_references() -> None:
    """No file outside spec_009/ and .skilmarillion/ references any deleted symbol."""
    compiled = [(sym, re.compile(sym)) for sym in DELETED_SYMBOLS]
    violations: list[str] = []

    for path in _collect_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for sym, pattern in compiled:
            matches = pattern.findall(text)
            if matches:
                rel = str(path.relative_to(REPO_ROOT))
                violations.append(f"{rel}: found {len(matches)} match(es) for {sym!r}")

    assert violations == [], (
        "Deleted symbols still referenced outside excluded dirs:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
