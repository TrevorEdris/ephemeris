"""Tests for scripts/ingest/graphiti_client.py — path + state helpers.

The async ``get_graphiti`` factory is not covered here because it imports
graphiti-core, which is a heavy dep not required for unit tests of the
deterministic paths.
"""

import os
from pathlib import Path

from ingest.graphiti_client import (
    DEFAULT_DB_PATH,
    STATE_DIR,
    default_db_path,
    ensure_state_dir,
)


def test_default_db_path_respects_env_override(tmp_path, monkeypatch):
    override = tmp_path / "custom-db"
    monkeypatch.setenv("EPHEMERIS_DB_PATH", str(override))
    assert default_db_path() == str(override)


def test_default_db_path_expands_tilde(monkeypatch):
    monkeypatch.setenv("EPHEMERIS_DB_PATH", "~/foo-ephem-db-test")
    result = default_db_path()
    assert "~" not in result
    assert result.endswith("foo-ephem-db-test")


def test_default_db_path_defaults_to_home(monkeypatch):
    monkeypatch.delenv("EPHEMERIS_DB_PATH", raising=False)
    assert default_db_path() == str(DEFAULT_DB_PATH)


def test_ensure_state_dir_creates_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # Re-import to pick up new HOME
    from importlib import reload

    import ingest.graphiti_client as gc

    reload(gc)
    created = gc.ensure_state_dir()
    assert created.exists()
    assert created.is_dir()
    assert created == fake_home / ".ai" / "ephemeris" / "state"


def test_state_dir_constant_under_home():
    assert str(STATE_DIR).endswith(".ai/ephemeris/state")
