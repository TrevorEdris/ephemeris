"""SPEC-002 hook integration tests.

Spawns hook subprocesses with real transcript files and a real tmp staging
dir to verify end-to-end behaviour, including the N-5 gap: successful
capture must produce empty stderr.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
POST_SESSION_PY = REPO_ROOT / "hooks" / "post_session.py"
PRE_COMPACT_PY = REPO_ROOT / "hooks" / "pre_compact.py"


def _run_hook(
    script: Path,
    payload: dict,
    staging_root: Path,
) -> "subprocess.CompletedProcess[bytes]":
    import subprocess

    env = {**os.environ, "EPHEMERIS_STAGING_ROOT": str(staging_root)}
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=10,
        env=env,
    )


# ---------------------------------------------------------------------------
# Fix 6: N-5 — successful capture path emits no stderr
# ---------------------------------------------------------------------------


def test_post_session_successful_capture_no_stderr(tmp_path: Path) -> None:
    """N-5: post_session.py successful capture exits 0, empty stderr, valid JSON stdout."""
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"hello"}\n')

    staging_root = tmp_path / "staging"
    session_id = "integ-no-stderr-001"
    payload = {"session_id": session_id, "transcript_path": str(transcript_file)}

    result = _run_hook(POST_SESSION_PY, payload, staging_root)

    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}; stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"Expected empty stderr on success, got: {result.stderr.decode()!r}"
    )

    # stdout must be valid JSON
    stdout_json = json.loads(result.stdout.decode())
    assert stdout_json.get("ok") is True, f"Expected ok=true in stdout JSON: {stdout_json}"

    # Capture file must exist at expected path
    capture_path = staging_root / "session-end" / f"{session_id}.jsonl"
    assert capture_path.exists(), f"Expected capture file at {capture_path}"
    assert capture_path.read_bytes() == transcript_file.read_bytes()


def test_pre_compact_successful_capture_no_stderr(tmp_path: Path) -> None:
    """N-5: pre_compact.py successful capture exits 0, empty stderr, valid JSON stdout."""
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_bytes(b'{"role":"assistant","content":"compacting"}\n')

    staging_root = tmp_path / "staging"
    session_id = "integ-no-stderr-002"
    payload = {"session_id": session_id, "transcript_path": str(transcript_file)}

    result = _run_hook(PRE_COMPACT_PY, payload, staging_root)

    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}; stderr: {result.stderr.decode()!r}"
    )
    assert result.stderr == b"", (
        f"Expected empty stderr on success, got: {result.stderr.decode()!r}"
    )

    # stdout must be valid JSON
    stdout_json = json.loads(result.stdout.decode())
    assert stdout_json.get("ok") is True, f"Expected ok=true in stdout JSON: {stdout_json}"

    # Capture file must exist at expected path
    capture_path = staging_root / "pre-compact" / f"{session_id}.jsonl"
    assert capture_path.exists(), f"Expected capture file at {capture_path}"
    assert capture_path.read_bytes() == transcript_file.read_bytes()
