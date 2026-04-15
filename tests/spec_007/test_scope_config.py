"""tests/spec_007/test_scope_config.py — SPEC-007 scope config loader tests.

Covers:
    load_scope_config: absent file, valid JSON, invalid JSON, wrong schema,
                       pattern normalization (trim/filter empty).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# AC-1 / load_scope_config — absent file
# ---------------------------------------------------------------------------

class TestLoadScopeConfigAbsentFile:
    """Returns empty ScopeConfig when the config file does not exist."""

    def test_load_scope_config_returns_empty_when_file_absent(self, tmp_path, monkeypatch):
        """EPHEMERIS_SCOPE_CONFIG pointing to nonexistent path → empty config."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        absent = str(tmp_path / "no_such_file.json")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", absent)

        cfg = load_scope_config()
        assert cfg == ScopeConfig(include=[], exclude=[])


# ---------------------------------------------------------------------------
# AC-2 / load_scope_config — valid JSON
# ---------------------------------------------------------------------------

class TestLoadScopeConfigValidJson:
    """Parses valid JSON and returns correct ScopeConfig."""

    def test_load_scope_config_parses_valid_json(self, tmp_path, monkeypatch):
        """Valid JSON with include and exclude lists parsed correctly."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        config_file = tmp_path / "scope.json"
        config_file.write_text(
            json.dumps({
                "include": ["/a/b/**", "/c/d/**"],
                "exclude": ["/a/b/secret/**"],
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(config_file))

        cfg = load_scope_config()
        assert cfg == ScopeConfig(
            include=["/a/b/**", "/c/d/**"],
            exclude=["/a/b/secret/**"],
        )

    def test_load_scope_config_empty_lists_parsed(self, tmp_path, monkeypatch):
        """Config with empty include/exclude lists parses to empty ScopeConfig."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        config_file = tmp_path / "scope.json"
        config_file.write_text(json.dumps({"include": [], "exclude": []}), encoding="utf-8")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(config_file))

        cfg = load_scope_config()
        assert cfg == ScopeConfig(include=[], exclude=[])

    def test_load_scope_config_include_only(self, tmp_path, monkeypatch):
        """Config with only include key parses; exclude defaults to empty."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        config_file = tmp_path / "scope.json"
        config_file.write_text(json.dumps({"include": ["/work/**"]}), encoding="utf-8")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(config_file))

        cfg = load_scope_config()
        assert cfg == ScopeConfig(include=["/work/**"], exclude=[])

    def test_load_scope_config_exclude_only(self, tmp_path, monkeypatch):
        """Config with only exclude key parses; include defaults to empty."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        config_file = tmp_path / "scope.json"
        config_file.write_text(json.dumps({"exclude": ["/secret/**"]}), encoding="utf-8")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(config_file))

        cfg = load_scope_config()
        assert cfg == ScopeConfig(include=[], exclude=["/secret/**"])


# ---------------------------------------------------------------------------
# AC-5 / load_scope_config — invalid JSON → empty + warning
# ---------------------------------------------------------------------------

class TestLoadScopeConfigInvalidJson:
    """Returns empty config and logs a warning when JSON is malformed."""

    def test_load_scope_config_invalid_json_returns_empty_with_warning(
        self, tmp_path, monkeypatch, caplog
    ):
        """Malformed JSON file → empty ScopeConfig + WARN log line."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        bad_file = tmp_path / "scope.json"
        bad_file.write_text("not-json{", encoding="utf-8")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(bad_file))

        with caplog.at_level(logging.WARNING, logger="ephemeris.scope"):
            cfg = load_scope_config()

        assert cfg == ScopeConfig(include=[], exclude=[])
        assert any(
            "invalid JSON" in rec.message or "invalid json" in rec.message.lower()
            for rec in caplog.records
        ), f"Expected 'invalid JSON' warning, got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# AC-5 / load_scope_config — wrong schema → empty + warning
# ---------------------------------------------------------------------------

class TestLoadScopeConfigWrongSchema:
    """Returns empty config and logs a warning when schema is unexpected."""

    def test_load_scope_config_wrong_schema_include_not_list_returns_empty_with_warning(
        self, tmp_path, monkeypatch, caplog
    ):
        """JSON with include as string (not list) → empty ScopeConfig + WARN."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        bad_file = tmp_path / "scope.json"
        bad_file.write_text(
            json.dumps({"include": "not a list", "exclude": []}), encoding="utf-8"
        )
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(bad_file))

        with caplog.at_level(logging.WARNING, logger="ephemeris.scope"):
            cfg = load_scope_config()

        assert cfg == ScopeConfig(include=[], exclude=[])
        assert any(
            "schema" in rec.message.lower() or "unexpected" in rec.message.lower()
            or "invalid" in rec.message.lower()
            for rec in caplog.records
        ), f"Expected schema warning, got: {[r.message for r in caplog.records]}"

    def test_load_scope_config_wrong_schema_exclude_not_list_returns_empty_with_warning(
        self, tmp_path, monkeypatch, caplog
    ):
        """JSON with exclude as int → empty ScopeConfig + WARN."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        bad_file = tmp_path / "scope.json"
        bad_file.write_text(
            json.dumps({"include": [], "exclude": 42}), encoding="utf-8"
        )
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(bad_file))

        with caplog.at_level(logging.WARNING, logger="ephemeris.scope"):
            cfg = load_scope_config()

        assert cfg == ScopeConfig(include=[], exclude=[])
        assert len(caplog.records) >= 1

    def test_load_scope_config_root_not_dict_returns_empty_with_warning(
        self, tmp_path, monkeypatch, caplog
    ):
        """JSON root is a list, not an object → empty ScopeConfig + WARN."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        bad_file = tmp_path / "scope.json"
        bad_file.write_text(json.dumps(["/a/**"]), encoding="utf-8")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(bad_file))

        with caplog.at_level(logging.WARNING, logger="ephemeris.scope"):
            cfg = load_scope_config()

        assert cfg == ScopeConfig(include=[], exclude=[])
        assert len(caplog.records) >= 1


# ---------------------------------------------------------------------------
# load_scope_config — pattern normalization
# ---------------------------------------------------------------------------

class TestLoadScopeConfigNormalizesPatterns:
    """Trims whitespace from patterns; filters out empty strings."""

    def test_load_scope_config_normalizes_patterns(self, tmp_path, monkeypatch):
        """Patterns with leading/trailing spaces and empty strings are cleaned."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        config_file = tmp_path / "scope.json"
        config_file.write_text(
            json.dumps({
                "include": ["  /a/b/**  ", "", "   ", "/c/**"],
                "exclude": ["/secret/**", ""],
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(config_file))

        cfg = load_scope_config()
        assert cfg.include == ["/a/b/**", "/c/**"]
        assert cfg.exclude == ["/secret/**"]


# ---------------------------------------------------------------------------
# load_scope_config — explicit path argument
# ---------------------------------------------------------------------------

class TestLoadScopeConfigExplicitPath:
    """load_scope_config(path=...) uses the supplied path, ignoring env var."""

    def test_explicit_path_overrides_env(self, tmp_path, monkeypatch):
        """Explicit path arg takes priority over EPHEMERIS_SCOPE_CONFIG."""
        from ephemeris.scope import ScopeConfig, load_scope_config

        env_file = tmp_path / "env_scope.json"
        env_file.write_text(json.dumps({"include": ["/env/**"]}), encoding="utf-8")
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(env_file))

        explicit_file = tmp_path / "explicit_scope.json"
        explicit_file.write_text(json.dumps({"include": ["/explicit/**"]}), encoding="utf-8")

        cfg = load_scope_config(path=explicit_file)
        assert cfg == ScopeConfig(include=["/explicit/**"], exclude=[])


# ---------------------------------------------------------------------------
# MINOR 4 — EPHEMERIS_SCOPE_CONFIG must be absolute path
# ---------------------------------------------------------------------------

class TestLoadScopeConfigRelativePathRejected:
    """EPHEMERIS_SCOPE_CONFIG set to a relative path → warning logged, all-capture returned."""

    def test_relative_env_path_logs_warning_and_returns_empty(
        self, monkeypatch, caplog
    ):
        """RED: relative EPHEMERIS_SCOPE_CONFIG ('relative/scope.json') must be rejected
        with a warning and fall back to ScopeConfig() (all-capture default).
        """
        from ephemeris.scope import ScopeConfig, load_scope_config

        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", "relative/scope.json")

        with caplog.at_level(logging.WARNING, logger="ephemeris.scope"):
            cfg = load_scope_config()

        assert cfg == ScopeConfig(include=[], exclude=[]), (
            "Relative EPHEMERIS_SCOPE_CONFIG must fall back to all-capture default"
        )
        assert any(
            "relative" in rec.message.lower() or "absolute" in rec.message.lower()
            for rec in caplog.records
        ), f"Expected warning about relative/non-absolute path, got: {[r.message for r in caplog.records]}"
