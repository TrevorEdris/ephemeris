"""SPEC-014 — Cursor + citation dedup."""

from __future__ import annotations

import json
from pathlib import Path

from ephemeris.citations import append_citation, format_citation, is_cited
from ephemeris.cursor import Cursor
from ephemeris.sources.base import Locator


def _locator(identifier: str = "abc123") -> Locator:
    return Locator(
        path=Path("/tmp/x.jsonl"),
        kind="native-transcript",
        identifier=identifier,
        when="2026-04-26",
    )


def test_cursor_load_missing_returns_empty(tmp_path):
    c = Cursor.load(tmp_path / "absent.json")
    assert c.sources == {}


def test_cursor_update_and_save_roundtrip(tmp_path):
    path = tmp_path / "cursor.json"
    c = Cursor.load(path)
    loc = _locator("abc123")
    c.update("native", loc, source_mtime=1000.0, run_id="r1")
    c.save()
    raw = json.loads(path.read_text())
    assert raw["sources"]["native"]["abc123"]["last_seen_mtime"] == 1000.0
    assert raw["sources"]["native"]["abc123"]["last_run_id"] == "r1"
    assert raw["version"] == 1


def test_cursor_is_fresh(tmp_path):
    c = Cursor.load(tmp_path / "cursor.json")
    loc = _locator()
    assert not c.is_fresh("native", loc, 1000.0)
    c.update("native", loc, source_mtime=1000.0, run_id="r1")
    assert c.is_fresh("native", loc, 1000.0)
    assert c.is_fresh("native", loc, 999.0)
    assert not c.is_fresh("native", loc, 1001.0)


def test_cursor_load_malformed_returns_empty(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not-json\n", encoding="utf-8")
    c = Cursor.load(path)
    assert c.sources == {}


def test_format_citation_uses_kind_prefix():
    line = format_citation("2026-04-26", "native-transcript", "abc")
    assert line == "> Source: [2026-04-26 native-transcript:abc]"


def test_is_cited_matches_new_format():
    page = "## Sessions\n\n> Source: [2026-04-26 native-transcript:abc]\n"
    assert is_cited(page, "2026-04-26", "native-transcript", "abc")
    assert not is_cited(page, "2026-04-26", "native-transcript", "xyz")
    assert not is_cited(page, "2026-04-25", "native-transcript", "abc")


def test_is_cited_matches_legacy_format():
    page = "## Sessions\n\n> Source: [2026-04-26 abc-legacy]\n"
    # Legacy id-only format must still match — different kind tolerated.
    assert is_cited(page, "2026-04-26", "native-transcript", "abc-legacy")


def test_append_citation_dedups_repeat_calls():
    page = "# Foo\n\n## Sessions\n"
    once = append_citation(page, "2026-04-26", "native-transcript", "abc")
    twice = append_citation(once, "2026-04-26", "native-transcript", "abc")
    assert once.count("[2026-04-26 native-transcript:abc]") == 1
    assert once == twice


def test_append_citation_appends_when_absent():
    page = "# Foo\n"
    out = append_citation(page, "2026-04-26", "native-transcript", "abc")
    assert "Source: [2026-04-26 native-transcript:abc]" in out
