"""SPEC-015 — config + CLI integration."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ephemeris.config import (
    DEFAULT_CONFIG,
    EphemerisConfig,
    SourceSpec,
    load_config,
    _build_config,
)
from ephemeris.sources.native_transcript import NativeTranscriptSource
from ephemeris.sources.session_docs import SessionDocsSource


def test_default_config_has_only_native_source():
    assert len(DEFAULT_CONFIG["sources"]) == 1  # type: ignore[arg-type]
    src = DEFAULT_CONFIG["sources"][0]  # type: ignore[index]
    assert src["id"] == "native-claude-projects"
    assert src["kind"] == "native-transcript"
    assert src["root"] == "~/.claude/projects/"


def test_load_config_bootstraps_default(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "ephemeris.config.DEFAULT_CONFIG_PATH",
        cfg_path,
    )
    config = load_config(cfg_path)
    assert cfg_path.exists()
    assert len(config.sources) == 1
    assert config.sources[0].id == "native-claude-projects"
    assert isinstance(config.sources[0].source, NativeTranscriptSource)


def test_build_config_recognizes_session_docs_source():
    raw = {
        "version": 1,
        "wiki_root": "/tmp/wiki",
        "cursor_path": "/tmp/cursor.json",
        "sources": [
            {
                "id": "my-docs",
                "kind": "session-docs",
                "root": "/tmp/docs",
                "dir_pattern": r"^(\d{4}-\d{2}-\d{2})_(.+)$",
                "extractors": {
                    "PLAN.md": {"sections": ["Steps", "Risks"]},
                },
            }
        ],
    }
    config = _build_config(raw)
    assert len(config.sources) == 1
    spec = config.sources[0]
    assert spec.id == "my-docs"
    assert isinstance(spec.source, SessionDocsSource)
    assert spec.source.dir_pattern is not None
    assert "PLAN.md" in spec.source.extractors


def test_build_config_drops_unknown_kind():
    raw = {
        "sources": [
            {"id": "bad", "kind": "made-up", "root": "/tmp"},
        ]
    }
    config = _build_config(raw)
    assert config.sources == []


def test_build_config_tolerates_bad_dir_pattern():
    raw = {
        "sources": [
            {
                "id": "x",
                "kind": "session-docs",
                "root": "/tmp",
                "dir_pattern": "[unterminated",
            }
        ]
    }
    config = _build_config(raw)
    assert config.sources[0].source.dir_pattern is None


def test_cli_list_sources(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
    repo_root = Path(__file__).parent.parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ephemeris.cli",
            "--config",
            str(cfg_path),
            "list-sources",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "PYTHONPATH": str(repo_root),
        },
    )
    assert result.returncode == 0, result.stderr
    assert "native-claude-projects" in result.stdout
    assert "native-transcript" in result.stdout


def test_cli_cite_dedups(tmp_path):
    page = tmp_path / "TOPIC.md"
    page.write_text("# Topic\n\n## Sessions\n", encoding="utf-8")
    repo_root = Path(__file__).parent.parent.parent
    base_args = [
        sys.executable,
        "-m",
        "ephemeris.cli",
        "cite",
        "--page",
        str(page),
        "--when",
        "2026-04-26",
        "--kind",
        "native-transcript",
        "--identifier",
        "abc",
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHONPATH": str(repo_root),
    }
    r1 = subprocess.run(base_args, cwd=repo_root, capture_output=True, text=True, env=env)
    assert r1.returncode == 0
    assert "appended" in r1.stdout
    r2 = subprocess.run(base_args, cwd=repo_root, capture_output=True, text=True, env=env)
    assert r2.returncode == 0
    assert "already-present" in r2.stdout
    body = page.read_text()
    assert body.count("native-transcript:abc") == 1
