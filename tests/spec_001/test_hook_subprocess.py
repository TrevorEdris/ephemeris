"""Step 3 — Payload accessibility via subprocess invocation.

Asserts:
- Each hook script invoked as subprocess with minimal JSON stdin exits 0
- No stderr output on valid payload
- Each hook script invoked with empty stdin also exits 0
- No stderr output on empty stdin
- Each hook script invoked with malformed JSON stdin exits 0
- No stderr output on malformed JSON
- Hook stdout is always parseable JSON (all cases)
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POST_SESSION_PY = REPO_ROOT / "hooks" / "post_session.py"
PRE_COMPACT_PY = REPO_ROOT / "hooks" / "pre_compact.py"

VALID_PAYLOAD = b'{"session_id":"test-123"}'
EMPTY_PAYLOAD = b""
MALFORMED_PAYLOAD = b"{not valid json"


def _run_hook(script: Path, stdin_data: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin_data,
        capture_output=True,
        timeout=10,
    )


# --- post_session.py ---


def test_post_session_exits_zero_on_valid_payload() -> None:
    result = _run_hook(POST_SESSION_PY, VALID_PAYLOAD)
    assert result.returncode == 0, (
        f"post_session.py exited {result.returncode}; stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"post_session.py produced stderr: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_post_session_no_stderr_on_valid_payload() -> None:
    result = _run_hook(POST_SESSION_PY, VALID_PAYLOAD)
    assert result.stderr == b"", (
        f"post_session.py produced stderr: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_post_session_exits_zero_on_empty_stdin() -> None:
    result = _run_hook(POST_SESSION_PY, EMPTY_PAYLOAD)
    assert result.returncode == 0, (
        f"post_session.py exited {result.returncode} on empty stdin; "
        f"stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"post_session.py produced stderr on empty stdin: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_post_session_no_stderr_on_empty_stdin() -> None:
    result = _run_hook(POST_SESSION_PY, EMPTY_PAYLOAD)
    assert result.stderr == b"", (
        f"post_session.py produced stderr on empty stdin: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_post_session_exits_zero_on_malformed_json() -> None:
    result = _run_hook(POST_SESSION_PY, MALFORMED_PAYLOAD)
    assert result.returncode == 0, (
        f"post_session.py exited {result.returncode} on malformed JSON; "
        f"stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"post_session.py produced stderr on malformed JSON: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


# --- pre_compact.py ---


def test_pre_compact_exits_zero_on_valid_payload() -> None:
    result = _run_hook(PRE_COMPACT_PY, VALID_PAYLOAD)
    assert result.returncode == 0, (
        f"pre_compact.py exited {result.returncode}; stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"pre_compact.py produced stderr: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_pre_compact_no_stderr_on_valid_payload() -> None:
    result = _run_hook(PRE_COMPACT_PY, VALID_PAYLOAD)
    assert result.stderr == b"", (
        f"pre_compact.py produced stderr: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_pre_compact_exits_zero_on_empty_stdin() -> None:
    result = _run_hook(PRE_COMPACT_PY, EMPTY_PAYLOAD)
    assert result.returncode == 0, (
        f"pre_compact.py exited {result.returncode} on empty stdin; "
        f"stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"pre_compact.py produced stderr on empty stdin: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_pre_compact_no_stderr_on_empty_stdin() -> None:
    result = _run_hook(PRE_COMPACT_PY, EMPTY_PAYLOAD)
    assert result.stderr == b"", (
        f"pre_compact.py produced stderr on empty stdin: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)


def test_pre_compact_exits_zero_on_malformed_json() -> None:
    result = _run_hook(PRE_COMPACT_PY, MALFORMED_PAYLOAD)
    assert result.returncode == 0, (
        f"pre_compact.py exited {result.returncode} on malformed JSON; "
        f"stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"pre_compact.py produced stderr on malformed JSON: {result.stderr.decode()!r}"
    )
    json.loads(result.stdout)
