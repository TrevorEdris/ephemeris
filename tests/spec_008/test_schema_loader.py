"""tests/spec_008/test_schema_loader.py — SPEC-008: Custom Wiki Schema.

Unit tests for `load_user_schema` and `resolve_schema` in ephemeris/schema.py.

AC coverage:
    AC-1 (no user schema → default, no warning)
    AC-2 (valid user schema → used)
    AC-3 (user schema content appears verbatim in ## Wiki Schema block)
    AC-4 (empty file → default, silent)
    AC-5 (malformed/binary file → default + debug warning)
    AC-8 (> 64 KB → default + debug warning)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# AC-1: no user schema → default used silently
# ---------------------------------------------------------------------------

def test_resolve_schema_no_user_schema_returns_default(tmp_path: Path) -> None:
    """AC-1: When no user schema file exists, resolve_schema returns DEFAULT_SCHEMA.

    RED: fails because resolve_schema does not exist yet.
    """
    from ephemeris.schema import DEFAULT_SCHEMA, resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    # No EPHEMERIS_SCHEMA_PATH set, no ~/.claude/ephemeris/schema.md,
    # no wiki_root/SCHEMA.md → must fall back to DEFAULT_SCHEMA
    result = resolve_schema(wiki_root, user_schema_path=None)
    assert result == DEFAULT_SCHEMA


def test_resolve_schema_no_user_schema_no_debug_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-1: When falling back to DEFAULT_SCHEMA silently, no debug warnings logged."""
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    with caplog.at_level(logging.DEBUG, logger="ephemeris.schema"):
        resolve_schema(wiki_root, user_schema_path=None)

    # No warnings should be logged for a clean default fallback
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, f"Expected no warnings, got: {[r.message for r in warnings]}"


# ---------------------------------------------------------------------------
# AC-2: valid user schema → injected into prompt
# ---------------------------------------------------------------------------

def test_resolve_schema_valid_user_schema_returned(tmp_path: Path) -> None:
    """AC-2: A valid user schema file at user_schema_path is returned by resolve_schema.

    RED: fails because resolve_schema / load_user_schema do not exist yet.
    """
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_file = tmp_path / "my-schema.md"
    schema_file.write_text("# My Custom Schema\n\nPage type: cooking-recipe\n", encoding="utf-8")

    result = resolve_schema(wiki_root, user_schema_path=schema_file)
    assert "# My Custom Schema" in result
    assert "cooking-recipe" in result


def test_load_user_schema_valid_file(tmp_path: Path) -> None:
    """AC-2: load_user_schema returns file content for a valid file.

    RED: fails because load_user_schema does not exist yet.
    """
    from ephemeris.schema import load_user_schema

    schema_file = tmp_path / "schema.md"
    content = "# Custom\nMy schema content here.\n"
    schema_file.write_text(content, encoding="utf-8")

    result = load_user_schema(schema_file)
    assert result == content


# ---------------------------------------------------------------------------
# AC-3: user schema content appears verbatim in ## Wiki Schema block
# ---------------------------------------------------------------------------

def test_user_schema_appears_in_system_prompt(tmp_path: Path) -> None:
    """AC-3: resolve_schema result is embedded verbatim in build_system_prompt output.

    RED: fails because resolve_schema does not exist yet.
    """
    from ephemeris.prompts import build_system_prompt
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_file = tmp_path / "schema.md"
    user_schema_text = "# My Custom Schema\n\nCooking recipe page type.\n"
    schema_file.write_text(user_schema_text, encoding="utf-8")

    schema = resolve_schema(wiki_root, user_schema_path=schema_file)
    prompt = build_system_prompt(schema)

    # Must appear in the ## Wiki Schema block
    assert "## Wiki Schema" in prompt
    assert "My Custom Schema" in prompt
    assert "Cooking recipe page type" in prompt


# ---------------------------------------------------------------------------
# AC-4: empty file → default used silently
# ---------------------------------------------------------------------------

def test_resolve_schema_empty_file_returns_default(tmp_path: Path) -> None:
    """AC-4: An empty user schema file causes resolve_schema to fall back to DEFAULT_SCHEMA.

    RED: fails because resolve_schema does not exist yet.
    """
    from ephemeris.schema import DEFAULT_SCHEMA, resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_file = tmp_path / "empty-schema.md"
    schema_file.write_text("", encoding="utf-8")

    result = resolve_schema(wiki_root, user_schema_path=schema_file)
    assert result == DEFAULT_SCHEMA


def test_resolve_schema_empty_file_no_debug_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-4: Empty file fallback is silent (no debug warning logged)."""
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_file = tmp_path / "empty-schema.md"
    schema_file.write_text("", encoding="utf-8")

    with caplog.at_level(logging.DEBUG, logger="ephemeris.schema"):
        resolve_schema(wiki_root, user_schema_path=schema_file)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, f"Expected no warnings for empty file, got: {[r.message for r in warnings]}"


def test_load_user_schema_empty_file_returns_none(tmp_path: Path) -> None:
    """AC-4: load_user_schema returns None for an empty file."""
    from ephemeris.schema import load_user_schema

    schema_file = tmp_path / "empty.md"
    schema_file.write_text("", encoding="utf-8")

    result = load_user_schema(schema_file)
    assert result is None


# ---------------------------------------------------------------------------
# AC-5: malformed/binary file → default + debug warning
# ---------------------------------------------------------------------------

def test_resolve_schema_binary_file_returns_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-5: A binary/undecodable schema file → DEFAULT_SCHEMA + debug warning.

    RED: fails because resolve_schema does not exist yet.
    """
    from ephemeris.schema import DEFAULT_SCHEMA, resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_file = tmp_path / "bad-schema.md"
    # Write invalid UTF-8 bytes
    schema_file.write_bytes(b"\xff\xfe\x00\x01binary\x80\x90garbage")

    with caplog.at_level(logging.DEBUG, logger="ephemeris.schema"):
        result = resolve_schema(wiki_root, user_schema_path=schema_file)

    assert result == DEFAULT_SCHEMA

    # Must log a debug-level message mentioning the skip
    debug_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("bad-schema.md" in m or "decode" in m.lower() or "skip" in m.lower() or "malform" in m.lower() for m in debug_msgs), \
        f"Expected debug log about decode error, got: {debug_msgs}"


def test_load_user_schema_binary_file_returns_none(tmp_path: Path) -> None:
    """AC-5: load_user_schema returns None for binary/undecodable content."""
    from ephemeris.schema import load_user_schema

    schema_file = tmp_path / "bad.md"
    schema_file.write_bytes(b"\xff\xfe\x00\x01binary\x80\x90garbage")

    result = load_user_schema(schema_file)
    assert result is None


# ---------------------------------------------------------------------------
# AC-8: > 64 KB → default + debug warning
# ---------------------------------------------------------------------------

def test_resolve_schema_oversized_file_returns_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-8: A > 64 KB schema file → DEFAULT_SCHEMA + debug warning.

    RED: fails because resolve_schema does not exist yet.
    """
    from ephemeris.schema import DEFAULT_SCHEMA, resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_file = tmp_path / "huge-schema.md"
    # Write 65 KB of valid UTF-8 text
    schema_file.write_bytes(b"x" * (65 * 1024))

    with caplog.at_level(logging.DEBUG, logger="ephemeris.schema"):
        result = resolve_schema(wiki_root, user_schema_path=schema_file)

    assert result == DEFAULT_SCHEMA

    debug_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(
        "size" in m.lower() or "64" in m or "kb" in m.lower() or "skip" in m.lower()
        for m in debug_msgs
    ), f"Expected debug log about oversized file, got: {debug_msgs}"


def test_load_user_schema_oversized_file_returns_none(tmp_path: Path) -> None:
    """AC-8: load_user_schema returns None for a file exceeding 64 KB."""
    from ephemeris.schema import load_user_schema

    schema_file = tmp_path / "huge.md"
    schema_file.write_bytes(b"x" * (65 * 1024))

    result = load_user_schema(schema_file)
    assert result is None


# ---------------------------------------------------------------------------
# Env override: EPHEMERIS_SCHEMA_PATH takes precedence
# ---------------------------------------------------------------------------

def test_resolve_schema_env_override_takes_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EPHEMERIS_SCHEMA_PATH, when set and valid, overrides user_schema_path argument.

    RED: fails because resolve_schema doesn't check env var yet.
    """
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    env_schema = tmp_path / "env-schema.md"
    env_schema.write_text("# Env Schema\nFrom env var.\n", encoding="utf-8")

    arg_schema = tmp_path / "arg-schema.md"
    arg_schema.write_text("# Arg Schema\nFrom argument.\n", encoding="utf-8")

    monkeypatch.setenv("EPHEMERIS_SCHEMA_PATH", str(env_schema))

    result = resolve_schema(wiki_root, user_schema_path=arg_schema)
    assert "Env Schema" in result
    assert "From env var" in result


def test_resolve_schema_env_override_invalid_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EPHEMERIS_SCHEMA_PATH pointing at empty file falls through to next level.

    RED: fails because resolve_schema doesn't check env var yet.
    """
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    env_schema = tmp_path / "empty-env-schema.md"
    env_schema.write_text("", encoding="utf-8")

    arg_schema = tmp_path / "arg-schema.md"
    arg_schema.write_text("# Arg Schema\nActual content.\n", encoding="utf-8")

    monkeypatch.setenv("EPHEMERIS_SCHEMA_PATH", str(env_schema))

    result = resolve_schema(wiki_root, user_schema_path=arg_schema)
    # env schema is empty → fall through to arg_schema
    assert "Arg Schema" in result
    assert "Actual content" in result


# ---------------------------------------------------------------------------
# wiki_root/SCHEMA.md as level 3
# ---------------------------------------------------------------------------

def test_resolve_schema_uses_wiki_schema_md(tmp_path: Path) -> None:
    """Level 3: wiki_root/SCHEMA.md is used when no env var / user path is provided.

    RED: fails because resolve_schema does not exist yet.
    """
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / "SCHEMA.md").write_text("# Wiki-local Schema\nCustom for this wiki.\n", encoding="utf-8")

    result = resolve_schema(wiki_root, user_schema_path=None)
    assert "Wiki-local Schema" in result
    assert "Custom for this wiki" in result


def test_resolve_schema_user_path_overrides_wiki_schema(tmp_path: Path) -> None:
    """Level 2 beats Level 3: explicit user_schema_path overrides wiki_root/SCHEMA.md."""
    from ephemeris.schema import resolve_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / "SCHEMA.md").write_text("# Wiki Schema\nLocal schema.\n", encoding="utf-8")

    user_schema = tmp_path / "user.md"
    user_schema.write_text("# User Schema\nGlobal user schema.\n", encoding="utf-8")

    result = resolve_schema(wiki_root, user_schema_path=user_schema)
    assert "User Schema" in result
    assert "Global user schema" in result
