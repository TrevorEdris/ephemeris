"""exceptions.py — ephemeris domain exception hierarchy.

All public exceptions inherit from CaptureError, which itself inherits from
Exception so callers can catch at either granularity.
"""

from __future__ import annotations


class CaptureError(Exception):
    """Base class for all ephemeris capture errors."""


class EmptyTranscriptError(CaptureError):
    """Raised when the transcript file is empty, missing, or not referenced.

    Attributes:
        session_id: The session ID from the hook payload.
        hook_type: The hook type (e.g., 'pre-compact', 'session-end').
        detail: Human-readable description of the specific failure.
    """

    def __init__(self, session_id: str, hook_type: str, detail: str) -> None:
        super().__init__(
            f"Empty transcript for session {session_id!r} via {hook_type!r}: {detail}"
        )
        self.session_id = session_id
        self.hook_type = hook_type
        self.detail = detail


class InvalidPayloadError(CaptureError):
    """Raised when the hook payload is malformed or missing required fields."""


class StagingUnavailableError(CaptureError):
    """Raised when the staging directory cannot be created or written to."""


class TruncatedWriteError(CaptureError):
    """Raised when bytes written to staging differ from the source file size.

    Attributes:
        session_id: The session ID from the hook payload.
        hook_type: The hook type (e.g., 'pre-compact', 'session-end').
        expected: Expected byte count (source file size).
        actual: Actual byte count written.
    """

    def __init__(
        self, session_id: str, hook_type: str, expected: int, actual: int
    ) -> None:
        super().__init__(
            f"Truncated write for session {session_id!r} via {hook_type!r}: "
            f"expected {expected} bytes, wrote {actual} bytes"
        )
        self.session_id = session_id
        self.hook_type = hook_type
        self.expected = expected
        self.actual = actual
