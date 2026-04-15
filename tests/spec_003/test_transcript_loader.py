"""test_transcript_loader.py — Unit tests for ephemeris/transcript.py."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_transcript_returns_messages(tmp_path: Path) -> None:
    """load_transcript returns Message objects for each valid JSONL line."""
    from ephemeris.transcript import Message, load_transcript

    jsonl = tmp_path / "t.jsonl"
    jsonl.write_text(
        '{"type": "user", "content": "hello", "timestamp": "2026-04-15T10:00:00Z"}\n'
        '{"type": "assistant", "content": "hi there"}\n',
        encoding="utf-8",
    )

    msgs = load_transcript(jsonl)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "hello"
    assert msgs[0].timestamp == "2026-04-15T10:00:00Z"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "hi there"


def test_load_transcript_skips_malformed_lines(tmp_path: Path) -> None:
    """Malformed JSONL lines are silently skipped."""
    from ephemeris.transcript import load_transcript

    jsonl = tmp_path / "t.jsonl"
    jsonl.write_text(
        "NOT JSON AT ALL\n"
        '{"type": "user", "content": "valid"}\n'
        "[1, 2, 3]\n",
        encoding="utf-8",
    )

    msgs = load_transcript(jsonl)
    assert len(msgs) == 1
    assert msgs[0].content == "valid"


def test_load_transcript_returns_empty_for_missing_file(tmp_path: Path) -> None:
    """Missing file returns empty list instead of raising."""
    from ephemeris.transcript import load_transcript

    msgs = load_transcript(tmp_path / "nonexistent.jsonl")
    assert msgs == []


def test_transcript_to_text_includes_user_and_assistant(tmp_path: Path) -> None:
    """transcript_to_text includes user and assistant messages only."""
    from ephemeris.transcript import Message, transcript_to_text

    messages = [
        Message(role="system", content="Session started."),
        Message(role="user", content="What is the plan?"),
        Message(role="assistant", content="We will implement X."),
        Message(role="tool_use", content="some tool"),
    ]

    text = transcript_to_text(messages)
    assert "[USER]" in text
    assert "[ASSISTANT]" in text
    assert "What is the plan?" in text
    assert "We will implement X." in text
    assert "[SYSTEM]" not in text
    assert "[TOOL_USE]" not in text


def test_transcript_to_text_truncates_at_max_bytes(tmp_path: Path) -> None:
    """transcript_to_text truncates long transcripts at max_bytes."""
    from ephemeris.transcript import Message, transcript_to_text

    # Create a message that exceeds a small limit
    long_content = "A" * 1000
    messages = [Message(role="user", content=long_content)]

    text = transcript_to_text(messages, max_bytes=100)
    assert len(text.encode("utf-8")) <= 200  # truncated + truncation marker
    assert "TRUNCATED" in text


def test_load_transcript_fixture_simple() -> None:
    """Load the simple fixture and verify expected message count."""
    from ephemeris.transcript import load_transcript

    msgs = load_transcript(FIXTURES / "transcript_simple.jsonl")
    assert len(msgs) >= 4  # system + 3 user/assistant exchanges
    roles = {m.role for m in msgs}
    assert "user" in roles
    assert "assistant" in roles
