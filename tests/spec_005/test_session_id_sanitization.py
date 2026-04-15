"""tests/spec_005/test_session_id_sanitization.py — MINOR-2: session ID input sanitization.

RED tests: session IDs containing path separators or other unsafe characters
must be rejected with a non-zero exit and a sanitization error message.
"""
from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path

import pytest


def _run_main(args: list[str], env: dict) -> tuple[int, str, str]:
    from ephemeris.ingest import main

    captured_out = StringIO()
    captured_err = StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = captured_out
    sys.stderr = captured_err
    old_env = {}
    try:
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
        try:
            main(args)
            code = 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return code, captured_out.getvalue(), captured_err.getvalue()


def _base_env(tmp_path: Path) -> dict:
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    return {
        "EPHEMERIS_STAGING_ROOT": str(staging_root),
        "EPHEMERIS_WIKI_ROOT": str(wiki_root),
        "EPHEMERIS_LOG_PATH": str(tmp_path / "ephemeris.log"),
        "EPHEMERIS_MODEL_CLIENT": "fake",
    }


def test_ingest_command_session_id_with_path_separator_rejected(tmp_path: Path) -> None:
    """MINOR-2: session_id '../evil' must be rejected non-zero with sanitization error.

    RED: fails until main() validates session_id before passing to rglob.
    """
    code, out, err = _run_main(["../evil"], _base_env(tmp_path))

    assert code != 0, f"Expected non-zero exit for path-traversal session ID, got {code}"
    combined = out + err
    assert any(word in combined.lower() for word in ("invalid", "sanitiz", "session", "unsafe")), (
        f"Expected sanitization error message in output:\n{combined!r}"
    )


def test_ingest_command_session_id_with_forward_slash_rejected(tmp_path: Path) -> None:
    """MINOR-2: session_id 'foo/bar' must be rejected non-zero."""
    code, out, err = _run_main(["foo/bar"], _base_env(tmp_path))

    assert code != 0, f"Expected non-zero exit for slash-containing session ID, got {code}"


def test_ingest_command_session_id_with_null_byte_rejected(tmp_path: Path) -> None:
    """MINOR-2: session_id with null byte must be rejected non-zero."""
    code, out, err = _run_main(["foo\x00bar"], _base_env(tmp_path))

    assert code != 0, f"Expected non-zero exit for null-byte session ID, got {code}"


def test_ingest_command_session_id_empty_rejected(tmp_path: Path) -> None:
    """MINOR-2: empty session_id passed programmatically must be rejected.

    Note: argparse won't pass an empty positional arg via CLI, but main()
    receiving an empty string programmatically should still reject it.
    """
    code, out, err = _run_main([""], _base_env(tmp_path))

    assert code != 0, f"Expected non-zero exit for empty session ID, got {code}"


def test_ingest_command_valid_session_id_not_rejected(tmp_path: Path) -> None:
    """MINOR-2: a safe session ID must not be rejected by sanitization.

    A valid ID that doesn't exist in staging should still exit non-zero
    (no transcript found), but NOT due to sanitization error.
    """
    code, out, err = _run_main(["valid-session-2026-04-15"], _base_env(tmp_path))

    # Should fail with "no staged transcript found", not a sanitization error
    assert code != 0
    combined = out + err
    # Must NOT be a sanitization error — must be a "not found" error
    assert "valid-session-2026-04-15" in combined, (
        f"Expected session ID named in not-found error:\n{combined!r}"
    )
