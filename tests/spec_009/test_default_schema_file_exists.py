"""test_default_schema_file_exists.py — SPEC-009 AC-10, AC-20.

Asserts that schema/default.md exists at plugin root, is non-empty, and
contains a known stable heading from the prior DEFAULT_SCHEMA constant.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCHEMA_FILE = REPO_ROOT / "schema" / "default.md"

# Stable heading that must appear in the default schema
KNOWN_HEADING = "# Ephemeris Wiki Schema"
# A second anchor from the schema body
KNOWN_SECTION = "## Page Types"


def test_default_schema_file_exists() -> None:
    """schema/default.md must exist."""
    assert SCHEMA_FILE.exists(), (
        f"schema/default.md not found at {SCHEMA_FILE}"
    )


def test_default_schema_file_non_empty() -> None:
    """schema/default.md must not be empty."""
    assert SCHEMA_FILE.stat().st_size > 0, "schema/default.md is empty"


def test_default_schema_contains_known_heading() -> None:
    """schema/default.md must contain the wiki schema heading."""
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    assert KNOWN_HEADING in text, (
        f"schema/default.md is missing expected heading {KNOWN_HEADING!r}"
    )


def test_default_schema_contains_page_types_section() -> None:
    """schema/default.md must contain the Page Types section."""
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    assert KNOWN_SECTION in text, (
        f"schema/default.md is missing expected section {KNOWN_SECTION!r}"
    )
