"""transcript.py — JSONL transcript loader for ephemeris.

Loads a staged JSONL transcript file and returns a list of Message
dataclasses. Parsing is lenient — malformed lines are skipped.

Public API:
    Message             — dataclass(role, content, timestamp)
    load_transcript(path: Path) -> list[Message]
    transcript_to_text(messages: list[Message]) -> str
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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


def load_transcript(path: Path) -> list[Message]:
    """Load a JSONL transcript file into a list of Messages.

    Each line is parsed as a JSON object. Lines that are not valid JSON or
    that do not have a recognizable shape are silently skipped.

    Recognized shapes:
    - ``{"type": "<role>", "content": "<text>", ...}``

    Args:
        path: Path to the JSONL file. Must exist.

    Returns:
        List of Message objects, possibly empty if the file has no parseable
        lines or if no lines match the expected shape.
    """
    messages: list[Message] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return messages

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
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

    return messages


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
