"""Tests for scripts/ingest/ingest_sessions.py.

Covers only the deterministic pre-processing paths:
    - session dir parsing (date, ticket, slug)
    - file read + concat
    - --dry-run output
    - --validate-only checks
    - skip-if-only-SESSION rule
    - "latest" resolution

The async ``add_episode`` call itself is not exercised — it requires a live
Graphiti + LLM API key. Those paths are covered by P0-complete manual
verification steps, not unit tests.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from ingest import ingest_sessions


def make_session_dir(
    root: Path, slug: str, ticket: str | None, files: dict[str, str]
) -> Path:
    name = (
        f"{date.today().isoformat()}_{ticket}_{slug}"
        if ticket
        else f"{date.today().isoformat()}_{slug}"
    )
    d = root / name
    d.mkdir(parents=True)
    for name_, body in files.items():
        (d / name_).write_text(body)
    return d


def test_parse_session_dir_with_ticket(tmp_path):
    d = make_session_dir(tmp_path, "Taxonomy-Codes", "ENT-1240", {"SESSION.md": "x"})
    info = ingest_sessions.parse_session_dir(d)
    assert info.ticket == "ENT-1240"
    assert info.slug == "Taxonomy-Codes"
    assert info.date.isoformat() == date.today().isoformat()


def test_parse_session_dir_without_ticket(tmp_path):
    d = make_session_dir(tmp_path, "Refactor-Error-Handling", None, {"SESSION.md": "x"})
    info = ingest_sessions.parse_session_dir(d)
    assert info.ticket is None
    assert info.slug == "Refactor-Error-Handling"


def test_parse_session_dir_rejects_bad_name(tmp_path):
    bad = tmp_path / "not-a-session"
    bad.mkdir()
    with pytest.raises(ValueError):
        ingest_sessions.parse_session_dir(bad)


def test_read_session_files_concatenates_in_order(tmp_path):
    d = make_session_dir(
        tmp_path,
        "slug",
        None,
        {
            "SESSION.md": "SES_BODY\n",
            "DISCOVERY.md": "DISC_BODY\n",
            "PLAN.md": "PLAN_BODY\n",
        },
    )
    body = ingest_sessions.read_session_files(d)
    assert body.index("SES_BODY") < body.index("DISC_BODY") < body.index("PLAN_BODY")
    assert "# SESSION.md" in body
    assert "# DISCOVERY.md" in body
    assert "# PLAN.md" in body


def test_is_ingestable_requires_discovery_or_plan(tmp_path):
    session_only = make_session_dir(tmp_path, "a", None, {"SESSION.md": "x"})
    assert not ingest_sessions.is_ingestable(session_only)

    with_disc = make_session_dir(
        tmp_path, "b", None, {"SESSION.md": "x", "DISCOVERY.md": "y"}
    )
    assert ingest_sessions.is_ingestable(with_disc)

    with_plan = make_session_dir(
        tmp_path, "c", None, {"SESSION.md": "x", "PLAN.md": "y"}
    )
    assert ingest_sessions.is_ingestable(with_plan)


def test_resolve_latest_picks_most_recent(tmp_path, monkeypatch):
    # Three dirs with different date prefixes
    (tmp_path / "2026-01-01_A").mkdir()
    (tmp_path / "2026-01-01_A" / "SESSION.md").write_text("x")
    (tmp_path / "2026-03-15_B").mkdir()
    (tmp_path / "2026-03-15_B" / "SESSION.md").write_text("x")
    (tmp_path / "2026-04-01_C").mkdir()
    (tmp_path / "2026-04-01_C" / "SESSION.md").write_text("x")
    # Non-session dir — should be ignored
    (tmp_path / "stray").mkdir()

    latest = ingest_sessions.resolve_latest(tmp_path)
    assert latest.name == "2026-04-01_C"


def test_build_episode_preview_is_deterministic(tmp_path):
    d = make_session_dir(
        tmp_path,
        "slug",
        "ENT-1",
        {"SESSION.md": "a", "DISCOVERY.md": "b"},
    )
    preview = ingest_sessions.build_episode_preview(d)
    assert preview["name"].endswith("slug")
    assert preview["group_id"] == "workflow-knowledge"
    assert preview["ticket"] == "ENT-1"
    assert preview["reference_time"] == date.today().isoformat()
    assert "episode_body_excerpt" in preview
    assert "episode_body_bytes" in preview


def test_dry_run_emits_preview_json(tmp_path, capsys):
    d = make_session_dir(
        tmp_path,
        "slug",
        None,
        {"SESSION.md": "a", "DISCOVERY.md": "b"},
    )
    rc = ingest_sessions.main(["--dry-run", str(d)])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["group_id"] == "workflow-knowledge"
    assert payload["dry_run"] is True


def test_validate_only_rejects_empty_body(tmp_path, capsys):
    d = make_session_dir(tmp_path, "slug", None, {"SESSION.md": "", "DISCOVERY.md": ""})
    rc = ingest_sessions.main(["--validate-only", str(d)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "empty" in err.lower()


def test_validate_only_accepts_good_body(tmp_path, capsys):
    d = make_session_dir(
        tmp_path,
        "slug",
        None,
        {"SESSION.md": "real content", "DISCOVERY.md": "more real content"},
    )
    rc = ingest_sessions.main(["--validate-only", str(d)])
    assert rc == 0


def test_estimate_outputs_token_and_cost(tmp_path, capsys):
    d = make_session_dir(
        tmp_path,
        "slug",
        None,
        {"SESSION.md": "x" * 400, "DISCOVERY.md": "y" * 400},
    )
    rc = ingest_sessions.main(["--estimate", str(d)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "estimated_tokens" in payload
    assert "estimated_cost_usd" in payload
    assert payload["estimated_tokens"] > 0


def test_main_skips_non_ingestable_session(tmp_path, capsys):
    d = make_session_dir(tmp_path, "slug", None, {"SESSION.md": "x"})
    rc = ingest_sessions.main(["--dry-run", str(d)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "DISCOVERY.md" in err or "PLAN.md" in err


# --- /query "file this answer" path: synthetic episode from flags -----------


def test_episode_text_dry_run_builds_synthetic_preview(capsys):
    """--episode-text + --name should skip the session-dir path entirely
    and build a preview from the supplied text. Used by /query to file
    a synthesized answer back into the graph."""
    rc = ingest_sessions.main(
        [
            "--dry-run",
            "--episode-text",
            "We picked Kuzu because it is embedded and server-free.",
            "--name",
            "what backend did we pick",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["name"] == "what backend did we pick"
    assert payload["group_id"] == "workflow-knowledge"
    assert "Kuzu" in payload["episode_body_excerpt"]
    assert payload["source_description"] == "/query"


def test_episode_text_requires_name(capsys):
    rc = ingest_sessions.main(
        ["--dry-run", "--episode-text", "some answer"]
    )
    assert rc != 0
    err = capsys.readouterr().err
    assert "--name" in err


def test_episode_text_validate_rejects_empty(capsys):
    rc = ingest_sessions.main(
        ["--validate-only", "--episode-text", "   ", "--name", "q"]
    )
    assert rc != 0
    err = capsys.readouterr().err
    assert "empty" in err.lower()


def test_mark_ingested_creates_state_file(tmp_path, monkeypatch):
    """mark_ingested writes the session dir name into the state JSON file."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("EPHEMERIS_STATE_ROOT", str(state_dir))
    ingest_sessions.mark_ingested("2026-04-09_LLM-Wiki-Workflow")
    state_file = state_dir / "ingested-sessions.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert "2026-04-09_LLM-Wiki-Workflow" in data


def test_mark_ingested_is_idempotent(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("EPHEMERIS_STATE_ROOT", str(state_dir))
    ingest_sessions.mark_ingested("2026-04-09_test")
    ingest_sessions.mark_ingested("2026-04-09_test")  # second call must not dupe
    data = json.loads((state_dir / "ingested-sessions.json").read_text())
    assert data.count("2026-04-09_test") == 1


def test_episode_text_estimate_reports_tokens(capsys):
    rc = ingest_sessions.main(
        [
            "--estimate",
            "--episode-text",
            "a" * 800,
            "--name",
            "q",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["estimated_tokens"] > 0
    assert "estimated_cost_usd" in payload
