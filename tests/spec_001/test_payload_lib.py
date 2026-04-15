"""Direct unit tests for hooks/_lib/payload.py.

Tests read_payload() in-process using monkeypatched sys.stdin.
All tests must return normally — no exceptions should propagate.
"""

import io
import sys
from pathlib import Path

# Add hooks/ to sys.path so _lib.payload is importable without installing the package.
_HOOKS_DIR = str(Path(__file__).parent.parent.parent / "hooks")
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _lib.payload import read_payload  # noqa: E402


def test_read_payload_valid_json(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id":"abc"}'))
    assert read_payload() == {"session_id": "abc"}


def test_read_payload_empty_stdin(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert read_payload() == {}


def test_read_payload_malformed_json(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{not valid"))
    assert read_payload() == {}


def test_read_payload_missing_session_id(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('{"foo":"bar"}'))
    assert read_payload() == {"foo": "bar"}
