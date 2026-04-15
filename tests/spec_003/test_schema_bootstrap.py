"""test_schema_bootstrap.py — Slice 1: Schema Bootstrap tests.

Tests AC-1.1 through AC-1.4 of SPEC-003.
"""

from __future__ import annotations

from pathlib import Path


def test_bootstrap_writes_schema_on_first_run(tmp_path: Path) -> None:
    """AC-1.1: Given no wiki, bootstrap writes SCHEMA.md to wiki root."""
    from ephemeris.schema import bootstrap_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_path = wiki_root / "SCHEMA.md"

    assert not schema_path.exists()
    bootstrap_schema(wiki_root)
    assert schema_path.exists()
    assert schema_path.stat().st_size > 0
