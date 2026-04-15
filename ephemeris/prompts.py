"""prompts.py — Prompt construction and response parsing for ephemeris ingestion.

Builds the system and user prompts for the ingestion model call, then
parses the JSON response into a list of PageOperation dataclasses.

Public API:
    PageOperation  — dataclass for a single page create/update operation
    build_system_prompt(schema_text: str) -> str
    build_user_prompt(transcript_text: str, session_id: str, session_date: str) -> str
    parse_response(raw: str) -> list[PageOperation]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageOperation:
    """A single create-or-update operation for a wiki page.

    Attributes:
        action: 'create' or 'update'.
        page_type: 'topic', 'entity', or 'decision'.
        page_name: File stem / entry title. Topics use kebab-case;
                   entities use PascalCase; decisions use a title string.
        content: Dict of content fields (varies by page_type).
        cross_references: List of other page names this page references.
    """

    action: str
    page_type: str
    page_name: str
    content: dict[str, Any]
    cross_references: list[str] = field(default_factory=list)


_SYSTEM_PROMPT_TEMPLATE = """\
You are the ephemeris wiki ingestion engine. Your job is to read a session
transcript and extract structured knowledge to write into a personal markdown wiki.

## Wiki Schema
{schema}

## Output Format
Respond with ONLY valid JSON (no markdown, no explanation). Use this exact structure:

{{
  "operations": [
    {{
      "action": "create" | "update",
      "page_type": "topic" | "entity" | "decision",
      "page_name": "<kebab-case for topic, PascalCase for entity, descriptive title for decision>",
      "content": {{
        "overview": "...",        // topics: concise summary
        "details": "...",         // topics: extended discussion
        "role": "...",            // entities: what this component does
        "relationships": [        // entities: named relationships
          {{"entity": "...", "description": "..."}}
        ],
        "decision": "...",        // decision: what was decided
        "rationale": "...",       // decision: why
        "date": "YYYY-MM-DD"      // decision: when
      }},
      "cross_references": ["<other-page-name>"]
    }}
  ]
}}

If the transcript contains no extractable architectural knowledge (e.g., only
greetings or casual chat), return: {{"operations": []}}

Rules:
- Extract only decisions, patterns, architectural choices, and component knowledge.
- Ignore personal conversation, troubleshooting steps, and temporary context.
- Each operation's page_name must be unique within its page_type.
- cross_references must name pages that are also created in this response or
  known to exist (by name) in the wiki.
- Do NOT include the citation — the host adds it. Do NOT add > Source: lines.
"""


def build_system_prompt(schema_text: str) -> str:
    """Build the system prompt embedding the full wiki schema.

    The schema block is stable across calls, making it an excellent candidate
    for prompt caching (applied by AnthropicModelClient automatically).

    Args:
        schema_text: Contents of wiki/SCHEMA.md.

    Returns:
        Formatted system prompt string.
    """
    return _SYSTEM_PROMPT_TEMPLATE.format(schema=schema_text)


def build_user_prompt(
    transcript_text: str,
    session_id: str,
    session_date: str,
) -> str:
    """Build the per-transcript user prompt.

    Args:
        transcript_text: Plain-text transcript from transcript_to_text().
        session_id: The session identifier (for context).
        session_date: The session date in YYYY-MM-DD format.

    Returns:
        Formatted user prompt string.
    """
    return (
        f"Session date: {session_date}\n"
        f"Session ID: {session_id}\n\n"
        f"## Transcript\n\n{transcript_text}\n\n"
        f"Extract all architectural knowledge from this transcript and return "
        f"the operations JSON as specified."
    )


def parse_response(raw: str) -> list[PageOperation]:
    """Parse the model's JSON response into PageOperation objects.

    Args:
        raw: Raw string returned by ModelClient.invoke().

    Returns:
        List of PageOperation objects. Empty list if no operations.

    Raises:
        ParseResponseError: If raw is not valid JSON, or if the top-level
            structure is missing the 'operations' list, or if any operation
            is missing required fields.
    """
    from ephemeris.exceptions import ParseResponseError

    raw = raw.strip()
    if not raw:
        raise ParseResponseError("Model returned empty response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseResponseError(
            f"Model response is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ParseResponseError(
            f"Expected JSON object at top level, got {type(data).__name__}"
        )

    operations_raw = data.get("operations")
    if operations_raw is None:
        raise ParseResponseError("Response missing 'operations' key")
    if not isinstance(operations_raw, list):
        raise ParseResponseError(
            f"'operations' must be a list, got {type(operations_raw).__name__}"
        )

    operations: list[PageOperation] = []
    for i, op in enumerate(operations_raw):
        if not isinstance(op, dict):
            raise ParseResponseError(
                f"Operation {i} must be a dict, got {type(op).__name__}"
            )

        action = op.get("action", "")
        page_type = op.get("page_type", "")
        page_name = op.get("page_name", "")
        content = op.get("content", {})
        cross_references = op.get("cross_references", [])

        if action not in ("create", "update"):
            raise ParseResponseError(
                f"Operation {i}: invalid action {action!r}; must be 'create' or 'update'"
            )
        if page_type not in ("topic", "entity", "decision"):
            raise ParseResponseError(
                f"Operation {i}: invalid page_type {page_type!r}"
            )
        if not page_name:
            raise ParseResponseError(f"Operation {i}: page_name is empty")
        if not isinstance(content, dict):
            raise ParseResponseError(
                f"Operation {i}: content must be a dict"
            )
        if not isinstance(cross_references, list):
            cross_references = []

        operations.append(
            PageOperation(
                action=action,
                page_type=page_type,
                page_name=page_name,
                content=content,
                cross_references=[str(r) for r in cross_references],
            )
        )

    return operations
