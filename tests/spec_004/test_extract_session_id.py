"""tests/spec_004/test_extract_session_id.py — Unit tests for _extract_latest_session_id.

Verifies that the session ID extractor correctly parses citation lines from
wiki page content so that AnthropicModelClient.merge_topic passes the real
existing_session_id instead of "unknown".
"""
from __future__ import annotations


def test_extract_single_citation() -> None:
    """Single citation line returns its session ID."""
    from ephemeris.model import _extract_latest_session_id

    content = (
        "# My Topic\n\n"
        "Some content.\n\n"
        "## Sessions\n"
        "> Source: [2026-04-15 sess-abc123]\n"
    )
    assert _extract_latest_session_id(content) == "sess-abc123"


def test_extract_multiple_citations_returns_last() -> None:
    """With multiple citation lines, the last one is returned."""
    from ephemeris.model import _extract_latest_session_id

    content = (
        "# My Topic\n\n"
        "Some content.\n\n"
        "## Sessions\n"
        "> Source: [2026-04-10 sess-first]\n"
        "> Source: [2026-04-12 sess-middle]\n"
        "> Source: [2026-04-15 sess-latest]\n"
    )
    assert _extract_latest_session_id(content) == "sess-latest"


def test_extract_no_citation_returns_unknown() -> None:
    """No citation lines returns 'unknown'."""
    from ephemeris.model import _extract_latest_session_id

    content = "# My Topic\n\nSome content without any citation lines.\n"
    assert _extract_latest_session_id(content) == "unknown"


def test_extract_ignores_partial_citation_lines() -> None:
    """Lines that partially match but don't follow the exact format are ignored."""
    from ephemeris.model import _extract_latest_session_id

    content = (
        "# My Topic\n\n"
        "Source: not a citation\n"
        "> Source: [missing-date-format session]\n"
        "> Source: [2026-04-15 real-session]\n"
    )
    # Only the well-formed citation line should match
    result = _extract_latest_session_id(content)
    assert result == "real-session"
