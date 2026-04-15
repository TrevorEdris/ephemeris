"""Tests for hooks._lib.staging_root.resolve_staging_root() helper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure hooks package is importable
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))


# ---------------------------------------------------------------------------
# Fix 4 tests: staging root env var resolution (RED first)
# ---------------------------------------------------------------------------


def test_resolve_staging_root_returns_default_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset EPHEMERIS_STAGING_ROOT returns DEFAULT_STAGING_ROOT."""
    from _lib.staging_root import DEFAULT_STAGING_ROOT, resolve_staging_root

    monkeypatch.delenv("EPHEMERIS_STAGING_ROOT", raising=False)
    result = resolve_staging_root()
    assert result == DEFAULT_STAGING_ROOT


def test_resolve_staging_root_returns_default_when_env_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPHEMERIS_STAGING_ROOT='' must NOT resolve to CWD; returns None to signal invalid."""
    from _lib.staging_root import resolve_staging_root

    monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", "")
    result = resolve_staging_root()
    # An empty string is invalid; must return None (caller exits 0)
    assert result is None


def test_resolve_staging_root_returns_none_for_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPHEMERIS_STAGING_ROOT set to a relative path returns None."""
    from _lib.staging_root import resolve_staging_root

    monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", "relative/path")
    result = resolve_staging_root()
    assert result is None


def test_resolve_staging_root_returns_path_for_absolute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """EPHEMERIS_STAGING_ROOT set to an absolute path returns that Path."""
    from _lib.staging_root import resolve_staging_root

    monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(tmp_path))
    result = resolve_staging_root()
    assert result == tmp_path


def test_resolve_staging_root_expands_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPHEMERIS_STAGING_ROOT with ~ is expanded and returned."""
    from _lib.staging_root import resolve_staging_root

    monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", "~/.claude/ephemeris/staging")
    result = resolve_staging_root()
    assert result is not None
    assert result == Path("~/.claude/ephemeris/staging").expanduser()
    assert result.is_absolute()
