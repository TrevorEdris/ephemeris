"""capture.py — ephemeris transcript capture module.

Reads a transcript file referenced by a hook payload and persists its bytes
atomically to a staging directory keyed by hook_type and session_id.

Public API:
    capture(hook_type, payload, staging_root) -> Path
    parse_hook_payload(hook_type, payload) -> tuple[str, Path]
    stage_transcript(staging_root, hook_type, session_id, src) -> Path

Storage convention:
    <staging_root>/<hook_type>/<session_id>.jsonl
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def parse_hook_payload(
    hook_type: str,
    payload: dict[str, Any],
) -> tuple[str, Path]:
    """Parse and validate a hook payload, returning (session_id, transcript_path).

    Args:
        hook_type: Hook type string, e.g. 'pre-compact' or 'session-end'.
        payload: Parsed hook payload dict. Must contain 'session_id' (non-empty
            string) and 'transcript_path' (non-empty string pointing to an
            existing, non-empty JSONL file).

    Returns:
        A tuple of (session_id, transcript_path) where transcript_path is a
        resolved Path object confirmed to exist and contain data.

    Raises:
        InvalidPayloadError: If payload is not a dict, missing 'session_id',
            or 'session_id' is empty.
        EmptyTranscriptError: If 'transcript_path' is missing, empty, the file
            does not exist, or the file contains zero bytes.
    """
    from ephemeris.exceptions import EmptyTranscriptError, InvalidPayloadError

    if not isinstance(payload, dict):
        raise InvalidPayloadError(
            f"Payload must be a dict, got {type(payload).__name__!r}"
        )

    session_id = payload.get("session_id")
    if not session_id:
        raise InvalidPayloadError("Payload missing required field 'session_id'")

    transcript_path_str = payload.get("transcript_path")
    if transcript_path_str is not None and not isinstance(transcript_path_str, str):
        raise InvalidPayloadError(
            f"transcript_path must be a string, got {type(transcript_path_str).__name__!r}"
        )
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

    # Stat the file before reading to detect empty-file condition cheaply.
    if transcript_path.stat().st_size == 0:
        raise EmptyTranscriptError(
            session_id=str(session_id),
            hook_type=hook_type,
            detail=f"transcript file is empty: {transcript_path}",
        )

    return str(session_id), transcript_path


def stage_transcript(
    staging_root: Path,
    hook_type: str,
    session_id: str,
    src: Path,
) -> Path:
    """Atomically copy a transcript file to staging storage.

    Writes to a temp file in the destination directory, then performs an
    atomic rename (os.replace). This guarantees readers never see partial
    data and no orphaned partial files remain on crash.

    After the rename, the written byte count is verified against the source
    file size. A mismatch causes the staged file to be deleted and raises
    TruncatedWriteError.

    Args:
        staging_root: Root directory for staging storage.
        hook_type: Hook type string used as the subdirectory name.
        session_id: Session identifier used as the filename stem.
            Must not contain path separators or resolve outside the staging
            root. Raises InvalidPayloadError if either constraint is violated.
        src: Source transcript file path (must exist and be non-empty).

    Returns:
        Path to the staged file.

    Raises:
        InvalidPayloadError: If session_id contains path separators or would
            resolve to a path outside the staging directory.
        StagingUnavailableError: If the staging directory cannot be created
            or written to.
        TruncatedWriteError: If the number of bytes written does not match
            the source file size.
    """
    from ephemeris.exceptions import InvalidPayloadError, StagingUnavailableError, TruncatedWriteError

    # Layer 1: Reject session_id values that carry path components.
    # Path(session_id).name strips leading directories; if it differs from the
    # original the caller passed a value with path separators (e.g. '../evil'
    # or '/tmp/evil' or 'legit/../escape').
    safe_session_id = Path(session_id).name
    if safe_session_id != session_id:
        raise InvalidPayloadError(
            f"session_id contains path separators: {session_id!r}"
        )

    dest_dir = staging_root / hook_type
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StagingUnavailableError(
            f"Cannot create staging directory {dest_dir}: {exc}"
        ) from exc

    dest_path = dest_dir / f"{session_id}.jsonl"

    # Layer 2: Belt-and-suspenders containment check.  Resolve both paths and
    # verify dest_path is a descendant of dest_dir.  This catches symlink-based
    # escapes that Path.name alone cannot prevent.
    try:
        resolved_dest = dest_path.resolve()
        resolved_dir = dest_dir.resolve()
        resolved_dest.relative_to(resolved_dir)
    except ValueError as exc:
        raise InvalidPayloadError(
            f"session_id resolves outside staging directory: {session_id!r}"
        ) from exc
    source_bytes = src.read_bytes()

    # Atomic write: write to temp file in same dir, then rename.
    # Track tmp_path so we can unlink on any failure before os.replace.
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=dest_dir, delete=False, suffix=".tmp"
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(source_bytes)
    except OSError as exc:
        # Clean up the temp file if it was created before the failure.
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise StagingUnavailableError(
            f"Cannot write to staging directory {dest_dir}: {exc}"
        ) from exc

    try:
        os.replace(tmp_path, dest_path)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise StagingUnavailableError(
            f"Cannot stage transcript to {dest_path}: {exc}"
        ) from exc

    # Verify byte count to detect truncation.
    written_size = dest_path.stat().st_size
    if written_size != len(source_bytes):
        dest_path.unlink(missing_ok=True)
        raise TruncatedWriteError(
            session_id=session_id,
            hook_type=hook_type,
            expected=len(source_bytes),
            actual=written_size,
        )

    return dest_path


def capture(
    hook_type: str,
    payload: dict[str, Any],
    staging_root: Path,
) -> Path:
    """Capture a transcript from a hook payload to staging storage.

    Thin composition of parse_hook_payload() and stage_transcript().

    Args:
        hook_type: Hook type string, e.g. 'pre-compact' or 'session-end'.
        payload: Parsed hook payload dict containing 'session_id' and
            'transcript_path'.
        staging_root: Root directory for staging storage. Subdirectories are
            created on first use.

    Returns:
        Path to the staged file.

    Raises:
        InvalidPayloadError: Payload is not a dict or missing 'session_id'.
        EmptyTranscriptError: transcript_path missing, file absent, or empty.
        StagingUnavailableError: Staging directory cannot be created/written.
        TruncatedWriteError: Byte count mismatch after write.
    """
    session_id, transcript_path = parse_hook_payload(hook_type, payload)
    return stage_transcript(staging_root, hook_type, session_id, transcript_path)
