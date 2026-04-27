"""SPEC-012 — NativeTranscriptSource behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from ephemeris.scope import ScopeConfig
from ephemeris.sources.native_transcript import NativeTranscriptSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "native_projects"


def test_scan_yields_all_jsonl_when_filter_off():
    source = NativeTranscriptSource(filter_title_gen=False)
    locators = list(source.scan(FIXTURES))
    assert len(locators) == 3
    ids = {loc.identifier for loc in locators}
    assert "aaaaaaaa-1111-2222-3333-444444444444" in ids
    assert "bbbbbbbb-1111-2222-3333-555555555555" in ids
    assert "cccccccc-1111-2222-3333-666666666666" in ids


def test_scan_filters_title_gen_subsessions():
    source = NativeTranscriptSource(filter_title_gen=True)
    locators = list(source.scan(FIXTURES))
    ids = {loc.identifier for loc in locators}
    assert "bbbbbbbb-1111-2222-3333-555555555555" not in ids


def test_scan_respects_scope_exclude():
    scope = ScopeConfig(exclude=["/Users/test/test-app"])
    source = NativeTranscriptSource(scope=scope, filter_title_gen=False)
    locators = list(source.scan(FIXTURES))
    assert locators == []


def test_read_produces_ingest_unit_with_text():
    source = NativeTranscriptSource(filter_title_gen=False)
    locators = list(source.scan(FIXTURES))
    target = next(
        loc for loc in locators
        if loc.identifier == "aaaaaaaa-1111-2222-3333-444444444444"
    )
    unit = source.read(target)
    assert unit.locator.kind == "native-transcript"
    assert "[USER]" in unit.raw_text
    assert "[ASSISTANT]" in unit.raw_text
    assert "JWT tokens" in unit.raw_text
    assert unit.metadata["message_count"] >= 4


def test_read_handles_empty_transcript():
    source = NativeTranscriptSource(filter_title_gen=False)
    locators = list(source.scan(FIXTURES))
    empty = next(
        loc for loc in locators
        if loc.identifier == "cccccccc-1111-2222-3333-666666666666"
    )
    unit = source.read(empty)
    assert unit.raw_text == ""


def test_scan_returns_empty_when_root_missing(tmp_path):
    source = NativeTranscriptSource()
    assert list(source.scan(tmp_path / "does-not-exist")) == []
