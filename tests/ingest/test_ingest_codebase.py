"""Tests for scripts/ingest/ingest_codebase.py — pure processing only.

The live ``git log`` subprocess and the real ``add_episode`` call are not
exercised; tests feed fixture data into the pure functions directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingest import ingest_codebase as ic


# --- git log parsing --------------------------------------------------------


GIT_LOG_FIXTURE = """\
COMMIT::deadbeef1234567890abcdef1234567890abcdef::2026-03-01T10:00:00+00:00::Merge pull request #42 from feat/foo
SUBJECT::feat: add foo widget (#42)
BODY::This is the PR body.
With two lines.
FILES::src/foo.py
src/foo_test.py
--COMMIT--
COMMIT::cafebabe0000000000000000000000000000feed::2026-02-15T09:30:00+00:00::Merge pull request #40 from fix/bar
SUBJECT::fix: null-safety for bar
BODY::
FILES::src/bar.py
--COMMIT--
"""


def test_parse_git_log_output_extracts_multiple_commits():
    commits = ic.parse_git_log_output(GIT_LOG_FIXTURE)
    assert len(commits) == 2
    c0 = commits[0]
    assert c0["sha"].startswith("deadbeef")
    assert c0["subject"] == "feat: add foo widget (#42)"
    assert "PR body" in c0["body"]
    assert c0["files_changed"] == ["src/foo.py", "src/foo_test.py"]
    assert c0["authored_at"].startswith("2026-03-01")


def test_parse_git_log_output_handles_empty_body():
    commits = ic.parse_git_log_output(GIT_LOG_FIXTURE)
    assert commits[1]["body"] == ""
    assert commits[1]["files_changed"] == ["src/bar.py"]


def test_parse_git_log_output_empty_input():
    assert ic.parse_git_log_output("") == []


# --- ticket ref extraction --------------------------------------------------


def test_extract_ticket_refs_finds_jira_keys():
    refs = ic.extract_ticket_refs("fixes PROJ-123 and closes INFRA-7")
    assert set(refs) == {"PROJ-123", "INFRA-7"}


def test_extract_ticket_refs_dedups_and_sorts():
    refs = ic.extract_ticket_refs("PROJ-1 PROJ-1 ABC-9 PROJ-1")
    assert refs == ["ABC-9", "PROJ-1"]


def test_extract_ticket_refs_ignores_lowercase():
    refs = ic.extract_ticket_refs("see jira-9 and proj-1")
    assert refs == []


def test_extract_ticket_refs_empty_text():
    assert ic.extract_ticket_refs("") == []


# --- episode formatting -----------------------------------------------------


def _commit(
    subject="feat: add thing",
    body="",
    files=("src/a.py", "src/b.py"),
    sha="abc1234def5678900000000000000000000beef",
    when="2026-03-01T10:00:00+00:00",
):
    return {
        "sha": sha,
        "subject": subject,
        "body": body,
        "files_changed": list(files),
        "authored_at": when,
    }


def test_format_commit_episode_without_pr():
    body = ic.format_commit_episode(_commit(body="some context"))
    assert "feat: add thing" in body
    assert "some context" in body
    assert "Files changed" in body
    assert "src/a.py" in body


def test_format_commit_episode_with_pr_injects_pr_section():
    pr = {"number": 42, "title": "Add thing", "body": "Long PR body " * 50}
    body = ic.format_commit_episode(_commit(), pr=pr)
    assert "PR #42" in body
    assert "Add thing" in body


def test_format_commit_episode_caps_pr_body_to_2k():
    pr = {"number": 1, "title": "t", "body": "x" * 5000}
    body = ic.format_commit_episode(_commit(), pr=pr)
    # Only 2000 chars of PR body may land in the episode body
    assert body.count("x") <= 2000


def test_format_commit_episode_truncates_files_changed_to_20():
    files = [f"src/f{i}.py" for i in range(30)]
    body = ic.format_commit_episode(_commit(files=files))
    # Only first 20 files listed
    assert "src/f19.py" in body
    assert "src/f20.py" not in body


# --- episode preview --------------------------------------------------------


def test_build_episode_preview_shape():
    commit = _commit()
    preview = ic.build_episode_preview(commit)
    assert preview["name"].startswith("commit ")
    assert preview["group_id"] == "codebase-history"
    assert preview["reference_time"] == "2026-03-01T10:00:00+00:00"
    assert "episode_body_bytes" in preview
    assert "episode_body_excerpt" in preview


# --- CLI orchestration (validate-only, no git) ------------------------------


def test_main_validate_only_with_stubbed_fetch(monkeypatch, capsys):
    def fake_fetch(**_kwargs):
        return ic.parse_git_log_output(GIT_LOG_FIXTURE)

    monkeypatch.setattr(ic, "fetch_merge_commits", fake_fetch)
    rc = ic.main(["--validate-only"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["commits"] == 2
    assert payload["valid"] is True


def test_main_dry_run_emits_preview_list(monkeypatch, capsys):
    def fake_fetch(**_kwargs):
        return ic.parse_git_log_output(GIT_LOG_FIXTURE)

    monkeypatch.setattr(ic, "fetch_merge_commits", fake_fetch)
    rc = ic.main(["--dry-run"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert len(payload["previews"]) == 2
    assert all(p["group_id"] == "codebase-history" for p in payload["previews"])


def test_main_estimate_reports_total_cost(monkeypatch, capsys):
    def fake_fetch(**_kwargs):
        return ic.parse_git_log_output(GIT_LOG_FIXTURE)

    monkeypatch.setattr(ic, "fetch_merge_commits", fake_fetch)
    rc = ic.main(["--estimate"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["commits"] == 2
    assert payload["estimated_tokens_total"] > 0
    assert "estimated_cost_usd_total" in payload
