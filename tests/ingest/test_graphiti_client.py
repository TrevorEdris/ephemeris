"""Tests for scripts/ingest/graphiti_client.py — path + state helpers.

The async ``get_graphiti`` factory is not covered here because it imports
graphiti-core, which is a heavy dep not required for unit tests of the
deterministic paths.
"""

import os
from pathlib import Path

import pytest

from ingest.graphiti_client import (
    DEFAULT_DB_PATH,
    STATE_DIR,
    default_db_path,
    ensure_state_dir,
    llm_client_kind,
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


# --- llm_client_kind --------------------------------------------------------


def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("EPHEMERIS_LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_llm_client_kind_defaults_to_openai_when_nothing_set(monkeypatch):
    _clear_llm_env(monkeypatch)
    assert llm_client_kind() == "openai"


def test_llm_client_kind_picks_anthropic_when_only_anthropic_key_set(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert llm_client_kind() == "anthropic"


def test_llm_client_kind_picks_openai_when_only_openai_key_set(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_client_kind() == "openai"


def test_llm_client_kind_prefers_anthropic_when_both_keys_set(monkeypatch):
    """Both keys is the common case for users who want Claude reasoning +
    OpenAI embeddings. Anthropic wins for reasoning because the user
    opting in to the Anthropic key is the explicit signal."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_client_kind() == "anthropic"


def test_llm_client_kind_explicit_override_wins(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("EPHEMERIS_LLM_PROVIDER", "openai")
    assert llm_client_kind() == "openai"


def test_llm_client_kind_explicit_override_is_case_insensitive(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("EPHEMERIS_LLM_PROVIDER", "AnThRoPiC")
    assert llm_client_kind() == "anthropic"


def test_llm_client_kind_rejects_unknown_provider(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("EPHEMERIS_LLM_PROVIDER", "bard")
    with pytest.raises(ValueError, match="bard"):
        llm_client_kind()
