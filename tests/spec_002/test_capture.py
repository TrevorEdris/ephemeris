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
