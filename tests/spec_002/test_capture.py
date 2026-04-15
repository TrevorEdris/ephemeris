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
