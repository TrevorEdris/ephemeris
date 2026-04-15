"""SPEC-002: Transcript Capture tests.

Tests follow the TDD plan: RED commits add tests, GREEN commits add implementation.
All tests use tmp_path fixture — no real ~/.claude/ paths are touched.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Make ephemeris package importable from repo root (mirrors SPEC-001 pattern)
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Step 1 RED: valid PreCompact payload writes to staging
# ---------------------------------------------------------------------------


def test_capture_pre_compact_writes_transcript_to_staging(tmp_path: Path) -> None:
    """AC-1: PreCompact payload -> read transcript_path -> persist to staging."""
    from ephemeris.capture import capture

    # Write a fake JSONL transcript file
    jsonl_content = (
        b'{"role":"user","content":"hello"}\n'
        b'{"role":"assistant","content":"world"}\n'
    )
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_bytes(jsonl_content)

    payload = {
        "session_id": "abc-123",
        "transcript_path": str(transcript_file),
    }
    staging_root = tmp_path / "staging"

    capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    dest = staging_root / "pre-compact" / "abc-123.jsonl"
    assert dest.exists(), f"Expected staged file at {dest}"
    assert dest.read_bytes() == jsonl_content


# ---------------------------------------------------------------------------
# Step 3 RED: SessionEnd payload writes to session-end subdir
# ---------------------------------------------------------------------------


def test_capture_session_end_writes_to_session_end_subdir(tmp_path: Path) -> None:
    """AC-2: SessionEnd payload -> persists to session-end subdir."""
    from ephemeris.capture import capture

    jsonl_content = b'{"role":"user","content":"bye"}\n'
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_bytes(jsonl_content)

    payload = {
        "session_id": "sess-456",
        "transcript_path": str(transcript_file),
    }
    staging_root = tmp_path / "staging"

    capture(hook_type="session-end", payload=payload, staging_root=staging_root)

    dest = staging_root / "session-end" / "sess-456.jsonl"
    assert dest.exists(), f"Expected staged file at {dest}"
    assert dest.read_bytes() == jsonl_content


# ---------------------------------------------------------------------------
# Step 5 RED: Idempotent on identical content
# ---------------------------------------------------------------------------


def test_capture_idempotent_identical_content(tmp_path: Path) -> None:
    """AC-3: Calling capture twice with identical payload leaves exactly one file."""
    from ephemeris.capture import capture

    jsonl_content = b'{"role":"user","content":"idempotent"}\n'
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_file.write_bytes(jsonl_content)

    payload = {
        "session_id": "idem-001",
        "transcript_path": str(transcript_file),
    }
    staging_root = tmp_path / "staging"

    capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)
    capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    dest = staging_root / "pre-compact" / "idem-001.jsonl"
    assert dest.exists()
    assert dest.read_bytes() == jsonl_content
    # Exactly one file in the directory (no duplicate with different name)
    staged_files = list((staging_root / "pre-compact").iterdir())
    assert len(staged_files) == 1


# ---------------------------------------------------------------------------
# Step 7 RED: Differing content — second write wins
# ---------------------------------------------------------------------------


def test_capture_second_write_overwrites_first(tmp_path: Path) -> None:
    """AC-4: Second capture for same session_id with different content overwrites."""
    from ephemeris.capture import capture

    content_v1 = b'{"role":"user","content":"version 1"}\n'
    content_v2 = b'{"role":"user","content":"version 2"}\n{"role":"assistant","content":"ok"}\n'

    transcript_file = tmp_path / "transcript.jsonl"
    staging_root = tmp_path / "staging"

    # First capture
    transcript_file.write_bytes(content_v1)
    payload = {"session_id": "over-001", "transcript_path": str(transcript_file)}
    capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    # Second capture with different content
    transcript_file.write_bytes(content_v2)
    capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    dest = staging_root / "pre-compact" / "over-001.jsonl"
    assert dest.read_bytes() == content_v2, "Expected second capture to win"


# ---------------------------------------------------------------------------
# Step 9 RED: Empty transcript error
# ---------------------------------------------------------------------------


def test_capture_empty_transcript_raises(tmp_path: Path) -> None:
    """AC-5: Empty transcript file raises EmptyTranscriptError; no file written."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import CaptureError, EmptyTranscriptError

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_bytes(b"")

    payload = {"session_id": "empty-001", "transcript_path": str(empty_file)}
    staging_root = tmp_path / "staging"

    with pytest.raises(EmptyTranscriptError) as exc_info:
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert isinstance(exc_info.value, CaptureError)
    assert "empty-001" in str(exc_info.value)
    assert "pre-compact" in str(exc_info.value)

    # No file should be staged
    dest = staging_root / "pre-compact" / "empty-001.jsonl"
    assert not dest.exists(), "No staged file expected for empty transcript"


def test_capture_missing_transcript_path_raises(tmp_path: Path) -> None:
    """AC-5: Missing transcript_path key raises EmptyTranscriptError."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import EmptyTranscriptError

    payload = {"session_id": "empty-002"}
    staging_root = tmp_path / "staging"

    with pytest.raises(EmptyTranscriptError) as exc_info:
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert "empty-002" in str(exc_info.value)


def test_capture_nonexistent_transcript_path_raises(tmp_path: Path) -> None:
    """AC-5: transcript_path pointing to nonexistent file raises EmptyTranscriptError."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import EmptyTranscriptError

    payload = {
        "session_id": "empty-003",
        "transcript_path": str(tmp_path / "does_not_exist.jsonl"),
    }
    staging_root = tmp_path / "staging"

    with pytest.raises(EmptyTranscriptError) as exc_info:
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert "empty-003" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Steps 11 + 13 RED: Malformed payload and missing session_id
# ---------------------------------------------------------------------------


def test_capture_non_dict_payload_raises_invalid_payload(tmp_path: Path) -> None:
    """AC-6: Non-dict payload raises InvalidPayloadError; no file written."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import InvalidPayloadError

    staging_root = tmp_path / "staging"

    with pytest.raises(InvalidPayloadError):
        capture(hook_type="pre-compact", payload="not a dict", staging_root=staging_root)  # type: ignore[arg-type]

    assert not staging_root.exists(), "Staging dir should not be created for invalid payload"


def test_capture_missing_session_id_raises_invalid_payload(tmp_path: Path) -> None:
    """AC-6: Payload missing session_id raises InvalidPayloadError."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import CaptureError, InvalidPayloadError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user"}\n')
    payload = {"transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    with pytest.raises(InvalidPayloadError) as exc_info:
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert isinstance(exc_info.value, CaptureError)


def test_capture_empty_session_id_raises_invalid_payload(tmp_path: Path) -> None:
    """AC-6: Payload with empty string session_id raises InvalidPayloadError."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import InvalidPayloadError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user"}\n')
    payload = {"session_id": "", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    with pytest.raises(InvalidPayloadError):
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)


# ---------------------------------------------------------------------------
# Step 14 RED: 1 MB transcript captured without truncation
# ---------------------------------------------------------------------------


def test_capture_large_transcript_no_truncation(tmp_path: Path) -> None:
    """AC-7: ~1 MB transcript captured byte-for-byte, no truncation."""
    from ephemeris.capture import capture

    # Generate ~1 MB of JSONL content (10000 lines)
    lines = []
    for i in range(10000):
        lines.append(json.dumps({"role": "user", "content": f"message number {i:05d} with padding " + "x" * 80}))
    jsonl_content = ("\n".join(lines) + "\n").encode()
    assert len(jsonl_content) > 1_000_000, "Expected at least 1 MB of test data"

    transcript_file = tmp_path / "big_transcript.jsonl"
    transcript_file.write_bytes(jsonl_content)

    payload = {"session_id": "big-001", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    dest = staging_root / "pre-compact" / "big-001.jsonl"
    captured_bytes = dest.read_bytes()
    assert len(captured_bytes) == len(jsonl_content), (
        f"Truncation detected: expected {len(jsonl_content)} bytes, got {len(captured_bytes)}"
    )


# ---------------------------------------------------------------------------
# Step 16 RED: Staging dir unavailable raises StagingUnavailableError
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="chmod not reliable on Windows")
def test_capture_staging_unavailable_raises(tmp_path: Path) -> None:
    """AC-8: Unwritable staging root raises StagingUnavailableError; no partial file."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import StagingUnavailableError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user"}\n')

    # Create staging root as read-only so mkdir of subdir fails
    staging_root = tmp_path / "ro_staging"
    staging_root.mkdir()
    staging_root.chmod(0o555)

    payload = {"session_id": "perm-001", "transcript_path": str(transcript_file)}

    try:
        with pytest.raises(StagingUnavailableError):
            capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

        # No partial file should exist
        partial_files = list(staging_root.rglob("*.tmp"))
        assert partial_files == [], f"Partial files left behind: {partial_files}"
    finally:
        # Restore permissions so tmp_path cleanup works
        staging_root.chmod(0o755)


def test_capture_staging_unavailable_via_mock(tmp_path: Path) -> None:
    """AC-8: StagingUnavailableError raised when os.makedirs fails (cross-platform)."""
    from unittest.mock import patch

    from ephemeris.capture import capture
    from ephemeris.exceptions import StagingUnavailableError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user"}\n')

    payload = {"session_id": "perm-002", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    with patch("ephemeris.capture.Path.mkdir", side_effect=PermissionError("denied")):
        with pytest.raises(StagingUnavailableError) as exc_info:
            capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert "denied" in str(exc_info.value).lower() or "staging" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Step 18 RED: Same session_id via both hooks stored in separate paths
# ---------------------------------------------------------------------------


def test_capture_same_session_id_both_hooks_separate_paths(tmp_path: Path) -> None:
    """AC-9: Same session_id via PreCompact + SessionEnd stored in separate subdirs."""
    from ephemeris.capture import capture

    content_pre = b'{"role":"user","content":"before compact"}\n'
    content_end = b'{"role":"user","content":"after session"}\n'

    pre_file = tmp_path / "pre.jsonl"
    pre_file.write_bytes(content_pre)
    end_file = tmp_path / "end.jsonl"
    end_file.write_bytes(content_end)

    staging_root = tmp_path / "staging"
    session_id = "shared-001"

    capture(
        hook_type="pre-compact",
        payload={"session_id": session_id, "transcript_path": str(pre_file)},
        staging_root=staging_root,
    )
    capture(
        hook_type="session-end",
        payload={"session_id": session_id, "transcript_path": str(end_file)},
        staging_root=staging_root,
    )

    pre_dest = staging_root / "pre-compact" / f"{session_id}.jsonl"
    end_dest = staging_root / "session-end" / f"{session_id}.jsonl"

    assert pre_dest.exists(), "Pre-compact staged file should exist"
    assert end_dest.exists(), "Session-end staged file should exist"
    assert pre_dest.read_bytes() == content_pre
    assert end_dest.read_bytes() == content_end
    assert pre_dest != end_dest, "Files must be at distinct paths"


# ---------------------------------------------------------------------------
# Step 20 RED: Hook scripts invoke capture and exit 0
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
POST_SESSION_PY = REPO_ROOT / "hooks" / "post_session.py"
PRE_COMPACT_PY = REPO_ROOT / "hooks" / "pre_compact.py"


def _run_hook_with_staging(
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


def test_post_session_invokes_capture_and_exits_zero(tmp_path: Path) -> None:
    """Step 20: post_session.py runs capture via EPHEMERIS_STAGING_ROOT env var."""
    import subprocess

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"hi"}\n')

    staging_root = tmp_path / "staging"
    payload = {"session_id": "hook-001", "transcript_path": str(transcript_file)}

    result = _run_hook_with_staging(POST_SESSION_PY, payload, staging_root)

    assert result.returncode == 0, (
        f"post_session.py exited {result.returncode}; stderr: {result.stderr.decode()!r}"
    )
    dest = staging_root / "session-end" / "hook-001.jsonl"
    assert dest.exists(), f"Expected staged file at {dest}; stderr: {result.stderr.decode()!r}"


def test_pre_compact_invokes_capture_and_exits_zero(tmp_path: Path) -> None:
    """Step 20: pre_compact.py runs capture via EPHEMERIS_STAGING_ROOT env var."""
    import subprocess

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"compact me"}\n')

    staging_root = tmp_path / "staging"
    payload = {"session_id": "hook-002", "transcript_path": str(transcript_file)}

    result = _run_hook_with_staging(PRE_COMPACT_PY, payload, staging_root)

    assert result.returncode == 0, (
        f"pre_compact.py exited {result.returncode}; stderr: {result.stderr.decode()!r}"
    )
    dest = staging_root / "pre-compact" / "hook-002.jsonl"
    assert dest.exists(), f"Expected staged file at {dest}; stderr: {result.stderr.decode()!r}"


def test_post_session_exits_zero_on_capture_error(tmp_path: Path) -> None:
    """Step 20: post_session.py exits 0 even when capture fails (empty transcript)."""
    import subprocess

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_bytes(b"")

    staging_root = tmp_path / "staging"
    payload = {"session_id": "hook-err-001", "transcript_path": str(empty_file)}

    result = _run_hook_with_staging(POST_SESSION_PY, payload, staging_root)

    assert result.returncode == 0, (
        f"post_session.py should exit 0 even on capture error; "
        f"got {result.returncode}; stderr: {result.stderr.decode()!r}"
    )


def test_pre_compact_exits_zero_on_capture_error(tmp_path: Path) -> None:
    """Step 20: pre_compact.py exits 0 even when capture fails (empty transcript)."""
    import subprocess

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_bytes(b"")

    staging_root = tmp_path / "staging"
    payload = {"session_id": "hook-err-002", "transcript_path": str(empty_file)}

    result = _run_hook_with_staging(PRE_COMPACT_PY, payload, staging_root)

    assert result.returncode == 0, (
        f"pre_compact.py should exit 0 even on capture error; "
        f"got {result.returncode}; stderr: {result.stderr.decode()!r}"
    )


# ---------------------------------------------------------------------------
# Path traversal rejection tests (Fix 1)
# ---------------------------------------------------------------------------


def test_capture_rejects_session_id_with_path_separator(tmp_path: Path) -> None:
    """session_id containing '../' must raise InvalidPayloadError; no file written."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import InvalidPayloadError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"hi"}\n')

    payload = {"session_id": "../escape", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    with pytest.raises(InvalidPayloadError) as exc_info:
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert "path separator" in str(exc_info.value).lower() or "../escape" in str(exc_info.value)

    # No .jsonl file should have been written anywhere under staging_root
    if staging_root.exists():
        jsonl_files = list(staging_root.rglob("*.jsonl"))
        assert jsonl_files == [], f"No .jsonl files should be written; found: {jsonl_files}"


def test_capture_rejects_session_id_with_absolute_path(tmp_path: Path) -> None:
    """session_id that is an absolute path must raise InvalidPayloadError."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import InvalidPayloadError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"hi"}\n')

    payload = {"session_id": "/tmp/evil", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    with pytest.raises(InvalidPayloadError) as exc_info:
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    assert "/tmp/evil" in str(exc_info.value) or "path separator" in str(exc_info.value).lower()

    if staging_root.exists():
        jsonl_files = list(staging_root.rglob("*.jsonl"))
        assert jsonl_files == [], f"No .jsonl files should be written; found: {jsonl_files}"


def test_capture_rejects_session_id_with_parent_ref_as_suffix(tmp_path: Path) -> None:
    """session_id 'legit/../escape' must raise InvalidPayloadError."""
    from ephemeris.capture import capture
    from ephemeris.exceptions import InvalidPayloadError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"hi"}\n')

    payload = {"session_id": "legit/../escape", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"

    with pytest.raises(InvalidPayloadError):
        capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    if staging_root.exists():
        jsonl_files = list(staging_root.rglob("*.jsonl"))
        assert jsonl_files == [], f"No .jsonl files should be written; found: {jsonl_files}"


# ---------------------------------------------------------------------------
# Fix 3: tmp file cleaned up on write failure (RED first)
# ---------------------------------------------------------------------------


def test_capture_cleans_up_tmp_on_write_failure(tmp_path: Path) -> None:
    """AC-8: No .tmp file left behind when write fails before os.replace."""
    import tempfile
    from contextlib import contextmanager
    from unittest.mock import patch

    from ephemeris.capture import capture
    from ephemeris.exceptions import StagingUnavailableError

    transcript_file = tmp_path / "t.jsonl"
    transcript_file.write_bytes(b'{"role":"user","content":"hi"}\n')

    payload = {"session_id": "tmp-cleanup-001", "transcript_path": str(transcript_file)}
    staging_root = tmp_path / "staging"
    dest_dir = staging_root / "pre-compact"

    # Intercept NamedTemporaryFile: create the real file (so it exists on disk),
    # then raise OSError during write to simulate a mid-write failure.
    _real_ntf = tempfile.NamedTemporaryFile

    @contextmanager
    def _failing_ntf(**kwargs):  # type: ignore[no-untyped-def]
        # Create real temp file so it exists on disk
        real = _real_ntf(**kwargs)
        try:
            # Simulate the write raising before completion
            class _FailWriter:
                name = real.name

                def write(self, data):  # type: ignore[no-untyped-def]
                    raise OSError("simulated write failure")

                def __enter__(self):  # type: ignore[no-untyped-def]
                    return self

                def __exit__(self, *a):  # type: ignore[no-untyped-def]
                    real.close()

            yield _FailWriter()
        finally:
            real.close()

    with patch("ephemeris.capture.tempfile.NamedTemporaryFile", _failing_ntf):
        with pytest.raises(StagingUnavailableError):
            capture(hook_type="pre-compact", payload=payload, staging_root=staging_root)

    # No .tmp file should remain in the staging dest dir
    if dest_dir.exists():
        tmp_files = list(dest_dir.glob("*.tmp"))
        assert tmp_files == [], f"Orphaned .tmp files found: {tmp_files}"
