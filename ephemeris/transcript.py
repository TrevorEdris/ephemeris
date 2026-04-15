"""transcript.py — JSONL transcript loader for ephemeris.

Loads a staged JSONL transcript file and returns a TranscriptLoadResult
containing parsed Messages and the count of skipped malformed lines.
Parsing is lenient — malformed lines are skipped — but if every non-empty
line fails to parse, TranscriptParseError is raised to prevent a corrupt
file from being silently treated as empty.

Public API:
    Message               — dataclass(role, content, timestamp)
    TranscriptLoadResult  — dataclass(messages, skipped_lines)
    load_transcript(path: Path) -> TranscriptLoadResult
    transcript_to_text(messages: list[Message]) -> str
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Maximum bytes to pass to the model (~600KB ≈ 150K tokens)
_MAX_TEXT_BYTES = 600_000


@dataclass
class Message:
    """A single message from a Claude Code session transcript.

    Attributes:
        role: The message role — 'user', 'assistant', 'system', 'tool_use',
              'tool_result', or 'unknown'.
        content: The text content of the message. May be empty string.
        timestamp: ISO-8601 timestamp string, or empty string if absent.
    """

    role: str
    content: str
    timestamp: str = ""


@dataclass
class TranscriptLoadResult:
    """Result of loading a JSONL transcript file.

    Attributes:
        messages: Parsed Message objects.
        skipped_lines: Number of non-empty lines that failed to parse.
    """

    messages: list[Message] = field(default_factory=list)
    skipped_lines: int = 0


def load_transcript(path: Path) -> TranscriptLoadResult:
    """Load a JSONL transcript file into a TranscriptLoadResult.

    Each line is parsed as a JSON object. Lines that are not valid JSON or
    that do not have a recognizable shape are skipped; the count is recorded
    in ``TranscriptLoadResult.skipped_lines`` so callers can surface it.

    If every non-empty line is malformed (zero valid messages, at least one
    non-empty line), ``TranscriptParseError`` is raised. This prevents a
    completely corrupt file from being treated as an empty transcript.

    Recognized shapes:
    - ``{"type": "<role>", "content": "<text>", ...}``

    Args:
        path: Path to the JSONL file. Must exist.

    Returns:
        TranscriptLoadResult with parsed messages and skipped_lines count.

    Raises:
        TranscriptParseError: If the file has non-empty content but every
                              line fails to parse.
    """
    from ephemeris.exceptions import TranscriptParseError

    messages: list[Message] = []
    skipped_lines = 0
    non_empty_line_count = 0

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return TranscriptLoadResult()

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        non_empty_line_count += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped_lines += 1
            continue

        if not isinstance(obj, dict):
            skipped_lines += 1
            continue

        role = obj.get("type", "unknown")
        if not isinstance(role, str):
            role = "unknown"

        raw_content = obj.get("content", "")
        # Content may be a string or a list of content blocks
        if isinstance(raw_content, str):
            content = raw_content
        elif isinstance(raw_content, list):
            # Flatten list of content blocks into a single string
            parts: list[str] = []
            for block in raw_content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str) and text:
                        parts.append(text)
            content = "\n".join(parts)
        else:
            content = str(raw_content)

        timestamp = obj.get("timestamp", "")
        if not isinstance(timestamp, str):
            timestamp = ""

        messages.append(Message(role=role, content=content, timestamp=timestamp))

    # If the file had non-empty content but every line was malformed, raise.
    if non_empty_line_count > 0 and not messages:
        raise TranscriptParseError(
            f"All {non_empty_line_count} non-empty line(s) in {path} failed to parse"
        )

    return TranscriptLoadResult(messages=messages, skipped_lines=skipped_lines)


def transcript_to_text(messages: list[Message], max_bytes: int = _MAX_TEXT_BYTES) -> str:
    """Convert a list of Messages to a plain-text string suitable for the model prompt.

    Only user and assistant messages are included (system, tool_use, and
    tool_result messages are omitted to reduce noise). Messages are prefixed
    with their role in ``[ROLE]`` format.

    Output is truncated to ``max_bytes`` bytes if necessary, to respect the
    model's context window budget.

    Args:
        messages: List of Message objects from load_transcript.
        max_bytes: Maximum byte length of the returned text. Defaults to 600KB.

    Returns:
        Plain-text transcript suitable for embedding in a model prompt.
    """
    included_roles = {"user", "assistant"}
    lines: list[str] = []
    for msg in messages:
        if msg.role not in included_roles:
            continue
        if not msg.content.strip():
            continue
        lines.append(f"[{msg.role.upper()}] {msg.content}")

    text = "\n\n".join(lines)
    # Truncate to max_bytes to avoid exceeding the model context window
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", errors="ignore")
        text += "\n\n[TRANSCRIPT TRUNCATED]"
    return text
