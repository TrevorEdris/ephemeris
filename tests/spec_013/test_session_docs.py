"""SPEC-013 — SessionDocsSource behavior."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ephemeris.sources.session_docs import SectionExtractor, SessionDocsSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "session_docs"


def test_scan_with_pattern_yields_dated_locator():
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
    source = SessionDocsSource(dir_pattern=pattern)
    locators = list(source.scan(FIXTURES))
    assert len(locators) == 1
    loc = locators[0]
    assert loc.kind == "session-docs"
    assert loc.identifier == "Sample-Feature"
    assert loc.when == "2026-04-19"


def test_scan_without_pattern_uses_dir_name():
    source = SessionDocsSource()
    locators = list(source.scan(FIXTURES))
    assert len(locators) == 1
    assert locators[0].identifier == "2026-04-19_Sample-Feature"


def test_read_pass_through_includes_all_md():
    source = SessionDocsSource()
    locators = list(source.scan(FIXTURES))
    unit = source.read(locators[0])
    assert "=== SESSION.md ===" in unit.raw_text
    assert "=== DISCOVERY.md ===" in unit.raw_text
    assert "=== PLAN.md ===" in unit.raw_text
    assert unit.structured_sections == {}


def test_read_with_extractors_pulls_named_sections():
    source = SessionDocsSource(
        extractors={
            "DISCOVERY.md": SectionExtractor(sections=["Findings", "Open questions"]),
            "PLAN.md": SectionExtractor(sections=["Target files", "Risks"]),
        }
    )
    locators = list(source.scan(FIXTURES))
    unit = source.read(locators[0])
    assert "DISCOVERY.md:Findings" in unit.structured_sections
    assert "bcrypt" in unit.structured_sections["DISCOVERY.md:Findings"]
    assert "PLAN.md:Target files" in unit.structured_sections
    assert "auth/reset.go" in unit.structured_sections["PLAN.md:Target files"]


def test_read_extracts_wikilinks():
    source = SessionDocsSource()
    fixture_dir = Path(__file__).parent / "_wikilink_fixture"
    fixture_dir.mkdir(exist_ok=True)
    (fixture_dir / "NOTES.md").write_text(
        "# Notes\n\nSee [[2026-04-01_Other-Session]] and [[Other-Topic]].\n",
        encoding="utf-8",
    )
    try:
        locators = list(source.scan(fixture_dir.parent))
        target = next(loc for loc in locators if loc.identifier == "_wikilink_fixture")
        unit = source.read(target)
        refs = unit.metadata.get("references")
        assert refs is not None
        assert "2026-04-01_Other-Session" in refs
        assert "Other-Topic" in refs
    finally:
        for f in fixture_dir.iterdir():
            f.unlink()
        fixture_dir.rmdir()


def test_scan_skips_dirs_without_markdown(tmp_path):
    empty = tmp_path / "2026-01-01_Empty"
    empty.mkdir()
    source = SessionDocsSource()
    assert list(source.scan(tmp_path)) == []
