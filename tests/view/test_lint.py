"""Tests for scripts/view/lint.py — deterministic checks only.

The Graphiti-backed check (isolated nodes, live-query divergence) is
exercised by passing fixture data directly into the pure functions;
live graph calls are not part of the unit test surface.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from view import lint


# --- Filesystem / stale-page checks -----------------------------------------


def _mk_page(path: Path, body: str, *, mtime_days_ago: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    if mtime_days_ago:
        ts = time.time() - (mtime_days_ago * 86400)
        os.utime(path, (ts, ts))


def test_find_stale_pages_flags_old_files(tmp_path):
    _mk_page(tmp_path / "Decision" / "old.md", "---\ntype: Decision\n---\n", mtime_days_ago=45)
    _mk_page(tmp_path / "Decision" / "fresh.md", "---\ntype: Decision\n---\n", mtime_days_ago=2)

    findings = lint.find_stale_pages(tmp_path, max_age_days=30)
    paths = {f["path"] for f in findings}
    assert str(tmp_path / "Decision" / "old.md") in paths
    assert str(tmp_path / "Decision" / "fresh.md") not in paths


def test_find_stale_pages_skips_index_and_log(tmp_path):
    _mk_page(tmp_path / "index.md", "# index", mtime_days_ago=90)
    _mk_page(tmp_path / "log.md", "# log", mtime_days_ago=90)
    _mk_page(tmp_path / "Decision" / "d.md", "---\ntype: Decision\n---\n", mtime_days_ago=90)

    findings = lint.find_stale_pages(tmp_path, max_age_days=30)
    paths = {f["path"] for f in findings}
    assert str(tmp_path / "index.md") not in paths
    assert str(tmp_path / "log.md") not in paths
    assert str(tmp_path / "Decision" / "d.md") in paths


def test_find_stale_pages_reports_severity_and_check(tmp_path):
    _mk_page(tmp_path / "Decision" / "old.md", "x", mtime_days_ago=45)
    findings = lint.find_stale_pages(tmp_path, max_age_days=30)
    assert len(findings) == 1
    f = findings[0]
    assert f["check"] == "stale_page"
    assert f["severity"] == "warning"
    assert f["days_old"] >= 45


# --- Frontmatter parsing ----------------------------------------------------


def test_parse_frontmatter_extracts_fields():
    page = (
        "---\n"
        "type: Decision\n"
        "source_uuid: u-1\n"
        "graph_query: search_nodes(query='Use Kuzu')\n"
        "generated: 2026-04-10T12:00:00Z\n"
        "---\n"
        "\n"
        "body here\n"
    )
    fm = lint.parse_frontmatter(page)
    assert fm["type"] == "Decision"
    assert fm["source_uuid"] == "u-1"
    assert "search_nodes" in fm["graph_query"]


def test_parse_frontmatter_missing_returns_empty():
    assert lint.parse_frontmatter("no frontmatter here") == {}


# --- Isolated-node check ----------------------------------------------------


def test_check_isolated_nodes_flags_degree_zero():
    nodes = [
        {"uuid": "u-1", "name": "Use Kuzu", "degree": 0, "entity_type": "Decision"},
        {"uuid": "u-2", "name": "Empty body", "degree": 2, "entity_type": "Problem"},
        {"uuid": "u-3", "name": "Orphan", "degree": 0, "entity_type": "Decision"},
    ]
    findings = lint.check_isolated_nodes(nodes)
    uuids = {f["uuid"] for f in findings}
    assert uuids == {"u-1", "u-3"}
    assert all(f["check"] == "isolated_node" for f in findings)
    assert all(f["severity"] == "warning" for f in findings)


def test_check_isolated_nodes_empty_input():
    assert lint.check_isolated_nodes([]) == []


# --- Divergence check -------------------------------------------------------


def test_check_divergence_flags_missing_entities():
    page_views = [
        {"path": "Decision/use-kuzu.md", "source_uuid": "u-1", "live_matches": 1},
        {"path": "Decision/deleted.md", "source_uuid": "u-gone", "live_matches": 0},
        {"path": "Decision/superseded.md", "source_uuid": "u-2", "live_matches": 0},
    ]
    findings = lint.check_divergence(page_views)
    paths = {f["path"] for f in findings}
    assert paths == {"Decision/deleted.md", "Decision/superseded.md"}
    assert all(f["check"] == "divergence" for f in findings)


# --- Orchestration / CLI ---------------------------------------------------


def test_run_filesystem_checks_combines_stale_and_divergence(tmp_path):
    _mk_page(
        tmp_path / "Decision" / "old.md",
        "---\ntype: Decision\nsource_uuid: u-1\n---\n",
        mtime_days_ago=60,
    )
    findings = lint.run_filesystem_checks(tmp_path, max_age_days=30)
    kinds = {f["check"] for f in findings}
    assert "stale_page" in kinds


def test_main_default_emits_json(tmp_path, capsys):
    _mk_page(
        tmp_path / "Decision" / "old.md",
        "---\ntype: Decision\nsource_uuid: u-1\n---\n",
        mtime_days_ago=60,
    )
    rc = lint.main([
        "--wiki-root", str(tmp_path),
        "--no-graph",
        "--max-age-days", "30",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "findings" in payload
    assert any(f["check"] == "stale_page" for f in payload["findings"])


def test_main_pretty_renders_table(tmp_path, capsys):
    _mk_page(
        tmp_path / "Decision" / "old.md",
        "---\ntype: Decision\nsource_uuid: u-1\n---\n",
        mtime_days_ago=60,
    )
    rc = lint.main([
        "--wiki-root", str(tmp_path),
        "--no-graph",
        "--pretty",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "stale_page" in out
    assert "old.md" in out


def test_main_empty_wiki_returns_no_findings(tmp_path, capsys):
    rc = lint.main([
        "--wiki-root", str(tmp_path),
        "--no-graph",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []
