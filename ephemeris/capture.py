"""capture.py — ephemeris transcript capture module.

Reads a transcript file referenced by a hook payload and persists its bytes
atomically to a staging directory keyed by hook_type and session_id.

Public API:
    capture(hook_type, payload, staging_root) -> Path

Storage convention:
    <staging_root>/<hook_type>/<session_id>.jsonl
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def capture(
    hook_type: str,
    payload: dict[str, Any],
    staging_root: Path,
) -> Path:
    """Capture a transcript from a hook payload to staging storage.

    Reads the JSONL file at payload['transcript_path'] and writes its bytes
    atomically to <staging_root>/<hook_type>/<session_id>.jsonl.

    Args:
        hook_type: Hook type string, e.g. 'pre-compact' or 'session-end'.
        payload: Parsed hook payload dict containing 'session_id' and
            'transcript_path'.
        staging_root: Root directory for staging storage. Subdirectories are
            created on first use.

    Returns:
        Path to the staged file.

    Raises:
        InvalidPayloadError: If payload is not a dict, missing 'session_id',
            missing 'transcript_path', or 'session_id' is empty.
        EmptyTranscriptError: If transcript_path is empty string, the file
            does not exist, or the file contains zero bytes.
        StagingUnavailableError: If the staging directory cannot be created
            or written to (e.g., permission denied).
        TruncatedWriteError: If the number of bytes written does not match the
            source file size.
    """
    from ephemeris.exceptions import (
        EmptyTranscriptError,
        InvalidPayloadError,
        StagingUnavailableError,
        TruncatedWriteError,
    )

    # Validate payload shape
    if not isinstance(payload, dict):
        raise InvalidPayloadError(
            f"Payload must be a dict, got {type(payload).__name__!r}"
        )
    session_id = payload.get("session_id")
    if not session_id:
        raise InvalidPayloadError(
            "Payload missing required field 'session_id'"
        )
    transcript_path_str = payload.get("transcript_path")
    if not transcript_path_str:
        raise EmptyTranscriptError(
            session_id=str(session_id),
            hook_type=hook_type,
            detail="transcript_path is empty or missing",
        )

    transcript_path = Path(transcript_path_str)
    if not transcript_path.exists():
        raise EmptyTranscriptError(
            session_id=str(session_id),
            hook_type=hook_type,
            detail=f"transcript_path does not exist: {transcript_path}",
        )

    source_bytes = transcript_path.read_bytes()
    if len(source_bytes) == 0:
        raise EmptyTranscriptError(
            session_id=str(session_id),
            hook_type=hook_type,
            detail=f"transcript file is empty: {transcript_path}",
        )

    # Ensure staging directory exists
    dest_dir = staging_root / hook_type
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StagingUnavailableError(
            f"Cannot create staging directory {dest_dir}: {exc}"
        ) from exc

    dest_path = dest_dir / f"{session_id}.jsonl"

    # Atomic write: write to temp file in same dir, then rename
    try:
        with tempfile.NamedTemporaryFile(
            dir=dest_dir, delete=False, suffix=".tmp"
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(source_bytes)
    except OSError as exc:
        raise StagingUnavailableError(
            f"Cannot write to staging directory {dest_dir}: {exc}"
        ) from exc

    try:
        os.replace(tmp_path, dest_path)
    except OSError as exc:
        # Clean up temp file if rename fails
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise StagingUnavailableError(
            f"Cannot stage transcript to {dest_path}: {exc}"
        ) from exc

    # Verify byte count to detect truncation
    written_size = dest_path.stat().st_size
    if written_size != len(source_bytes):
        dest_path.unlink(missing_ok=True)
        raise TruncatedWriteError(
            session_id=str(session_id),
            hook_type=hook_type,
            expected=len(source_bytes),
            actual=written_size,
        )

    return dest_path
