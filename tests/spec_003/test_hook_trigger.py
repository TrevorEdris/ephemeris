"""test_hook_trigger.py — Slice 4: Hook trigger tests.

Tests that post_session.py spawns background ingestion on session end,
and that pre_compact.py does NOT spawn ingestion.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"
REPO_ROOT = Path(__file__).parent.parent.parent


def _run_hook(
    hook_script: str,
    payload: dict,
    env_overrides: dict | None = None,
) -> tuple[int, str, str]:
    """Run a hook script with a JSON payload on stdin.

    Returns:
        (returncode, stdout, stderr)
    """
    import subprocess

    env = os.environ.copy()
    env["EPHEMERIS_INGEST_ON_CAPTURE"] = "0"  # disable auto-ingest in tests
    if env_overrides:
        env.update(env_overrides)

    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook_script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_hook_spawns_background_ingestion_on_session_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4.1: post_session.py spawns python -m ephemeris.ingest as detached subprocess."""
    import subprocess

    # We run post_session.py in-process by importing its main() and
    # patching subprocess.Popen so we can assert it's called correctly.
    # We also need a real transcript file for the capture step to succeed.

    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_text('{"type": "user", "content": "hello"}\n', encoding="utf-8")

    staging_root = tmp_path / "staging"

    popen_calls: list[tuple] = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            popen_calls.append((args, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    payload = {
        "session_id": "hook-test-session",
        "transcript_path": str(transcript_file),
    }

    # Patch Popen and EPHEMERIS_INGEST_ON_CAPTURE via env
    with patch.dict(
        os.environ,
        {
            "EPHEMERIS_STAGING_ROOT": str(staging_root),
            "EPHEMERIS_INGEST_ON_CAPTURE": "1",  # enable for this test
        },
    ):
        with patch("subprocess.Popen", FakePopen):
            # Import and run post_session main directly
            import sys as _sys

            _sys.stdin = __import__("io").StringIO(json.dumps(payload))
            # We need to reload post_session since it reads from stdin at import
            import importlib
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "post_session_test", HOOKS_DIR / "post_session.py"
            )
            assert spec is not None
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None

            # Patch stdin for the hook's read_payload call
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = json.dumps(payload)
                try:
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
                    mod.main()
                except SystemExit:
                    pass

    # Verify Popen was called with python -m ephemeris.ingest
    assert len(popen_calls) >= 1, "subprocess.Popen must be called for background ingestion"
    popen_args = popen_calls[0][0][0]  # first positional arg of first call
    assert any("ephemeris.ingest" in str(arg) for arg in popen_args), (
        f"Popen command must include 'ephemeris.ingest', got: {popen_args}"
    )
    popen_kwargs = popen_calls[0][1]
    assert popen_kwargs.get("start_new_session") is True, (
        "Popen must use start_new_session=True for detached subprocess"
    )


def test_pre_compact_does_not_spawn_ingestion(
    tmp_path: Path,
) -> None:
    """AC: pre_compact.py does NOT trigger ingestion — fires mid-session."""
    import subprocess

    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_text('{"type": "user", "content": "hello"}\n', encoding="utf-8")

    staging_root = tmp_path / "staging"
    popen_calls: list = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            popen_calls.append((args, kwargs))

    payload = {
        "session_id": "compact-test-session",
        "transcript_path": str(transcript_file),
    }

    with patch.dict(
        os.environ,
        {
            "EPHEMERIS_STAGING_ROOT": str(staging_root),
            "EPHEMERIS_INGEST_ON_CAPTURE": "1",
        },
    ):
        with patch("subprocess.Popen", FakePopen):
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "pre_compact_test", HOOKS_DIR / "pre_compact.py"
            )
            assert spec is not None
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None

            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = json.dumps(payload)
                try:
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
                    mod.main()
                except SystemExit:
                    pass

    assert len(popen_calls) == 0, (
        "pre_compact.py must NOT spawn ingestion — fires mid-session"
    )
