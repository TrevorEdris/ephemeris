"""Tests for scripts/view/render.py — pure-data and template-rendering paths.

The Graphiti search calls are mocked at the ``fetch_entities`` /
``fetch_relationships`` boundary so tests run without a live DB.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from view import render


@pytest.fixture
def sample_entities():
    return [
        {
            "uuid": "u-1",
            "entity_type": "Decision",
            "title": "Use Kuzu",
            "fields": {
                "what": "Use Kuzu as the default backend",
                "why": "Embedded, zero-server dev",
                "alternatives": "Neo4j, FalkorDB",
            },
            "tags": ["backend"],
            "summary": "",
            "related": [],
        },
        {
            "uuid": "u-2",
            "entity_type": "Problem",
            "title": "Empty episode body",
            "fields": {"symptom": "Graphiti errors on empty body"},
            "tags": [],
            "summary": "",
            "related": [],
        },
    ]


def test_slugify_handles_spaces_and_punctuation():
    assert render.slugify("Use Kuzu!") == "use-kuzu"
    assert render.slugify("PROJ-1234: Fix bug") == "proj-1234-fix-bug"
    assert render.slugify("   multi   spaces   ") == "multi-spaces"


def test_group_by_type(sample_entities):
    grouped = render.group_by_type(sample_entities)
    assert set(grouped.keys()) == {"Decision", "Problem"}
    assert len(grouped["Decision"]) == 1
    assert len(grouped["Problem"]) == 1


def test_render_entity_page_uses_template(sample_entities):
    env = render.make_env()
    page = render.render_entity_page(
        env,
        sample_entities[0],
        group_id="workflow-knowledge",
        generated="2026-04-10T12:00:00Z",
    )
    assert "type: Decision" in page
    assert "workflow-knowledge" in page
    assert "Use Kuzu" in page
    assert "source of truth is Graphiti" in page
    assert "what" in page
    assert "Embedded, zero-server dev" in page


def test_render_index_page_groups_entities(sample_entities):
    env = render.make_env()
    page = render.render_index_page(
        env,
        sample_entities,
        group_id="workflow-knowledge",
        generated="2026-04-10T12:00:00Z",
    )
    assert "# ephemeris wiki" in page
    assert "Decision (1)" in page
    assert "Problem (1)" in page
    assert "Use Kuzu" in page


def test_render_log_entry_appends(sample_entities):
    env = render.make_env()
    entry = render.render_log_entry(
        env,
        group_id="workflow-knowledge",
        generated="2026-04-10T12:00:00Z",
        written=2,
        updated=1,
        total=5,
    )
    assert "## 2026-04-10T12:00:00Z" in entry
    assert "Pages written: 2" in entry
    assert "Pages updated: 1" in entry
    assert "Total after render: 5" in entry


def test_write_pages_to_disk(sample_entities, tmp_path):
    env = render.make_env()
    generated = "2026-04-10T12:00:00Z"
    result = render.write_pages(
        env,
        sample_entities,
        wiki_root=tmp_path,
        group_id="workflow-knowledge",
        generated=generated,
    )
    # Pages exist under type directories
    decision_file = tmp_path / "Decision" / "use-kuzu.md"
    problem_file = tmp_path / "Problem" / "empty-episode-body.md"
    assert decision_file.exists()
    assert problem_file.exists()
    # Index written
    assert (tmp_path / "index.md").exists()
    # Log written (append mode)
    assert (tmp_path / "log.md").exists()
    assert result["written"] == 2
    assert result["updated"] == 0
    assert result["total"] == 2


def test_write_pages_detects_updates(sample_entities, tmp_path):
    env = render.make_env()
    render.write_pages(
        env, sample_entities, tmp_path, "workflow-knowledge", "2026-04-10T12:00:00Z"
    )
    # Second render with changed content — should count as update
    sample_entities[0]["fields"]["why"] = "different reason"
    result = render.write_pages(
        env,
        sample_entities,
        tmp_path,
        "workflow-knowledge",
        "2026-04-10T12:01:00Z",
    )
    assert result["updated"] == 1
    assert result["written"] == 0


def test_log_appends_new_entries(sample_entities, tmp_path):
    env = render.make_env()
    render.write_pages(
        env, sample_entities, tmp_path, "workflow-knowledge", "2026-04-10T12:00:00Z"
    )
    render.write_pages(
        env, sample_entities, tmp_path, "workflow-knowledge", "2026-04-10T12:05:00Z"
    )
    log = (tmp_path / "log.md").read_text()
    assert "2026-04-10T12:00:00Z" in log
    assert "2026-04-10T12:05:00Z" in log
