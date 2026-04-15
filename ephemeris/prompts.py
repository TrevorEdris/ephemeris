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


_MERGE_SYSTEM_PROMPT = """\
You are the ephemeris wiki merge engine. Given EXISTING wiki page content and
NEW session content about the same topic, classify every fact/claim in NEW as
one of three categories:

- MERGE: a net-new fact not present in EXISTING — append to the page.
- DUPLICATE: a fact already present in EXISTING verbatim or semantically.
- CONFLICT: a fact that directly contradicts an existing claim in EXISTING.

Respond with ONLY valid JSON, no markdown, no explanation:

{
  "additions": ["net-new fact 1", "net-new fact 2"],
  "duplicates": ["repeated fact"],
  "conflicts": [
    {
      "existing_claim": "exact or near-exact claim from EXISTING",
      "new_claim": "contradicting claim from NEW"
    }
  ],
  "affirmed_claim": ""
}

If a conflict block (> ⚠️ Conflict:) exists in EXISTING and the NEW content
clearly affirms one side, set "affirmed_claim" to the affirmed text and return
that conflict's claims under "conflicts" so the resolver can remove the block.

Rules:
- Treat semantically equivalent claims as DUPLICATE even if worded differently.
- Treat factual contradictions (different values, opposite statements) as CONFLICT.
- Do NOT include the citation — the host adds it.
- Return empty arrays if no items in that category.
"""


def build_merge_prompt(existing: str, new: str, session_id: str) -> str:
    """Build the user prompt for the merge_topic model call.

    Args:
        existing: Current wiki page content.
        new: New session content to integrate.
        session_id: New session identifier (for context only).

    Returns:
        Formatted user prompt string.
    """
    return (
        f"Session ID: {session_id}\n\n"
        f"## Existing Wiki Page Content\n\n{existing}\n\n"
        f"## New Session Content\n\n{new}\n\n"
        f"Classify every fact/claim from the new session content as MERGE, "
        f"DUPLICATE, or CONFLICT relative to the existing page content."
    )


def parse_merge_response(raw: str, session_id: str, existing_session_id: str) -> "MergeResult":  # type: ignore[name-defined]  # noqa: F821
    """Parse the model's merge response into a MergeResult.

    Args:
        raw: Raw JSON string from ModelClient.invoke() for the merge call.
        session_id: New session identifier.
        existing_session_id: Session that authored the existing content.

    Returns:
        MergeResult with additions, duplicates, and conflicts.

    Raises:
        ParseResponseError: If raw is not valid JSON or missing required keys.
    """
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.model import ConflictPair, MergeResult

    raw = raw.strip()
    if not raw:
        raise ParseResponseError("Merge model returned empty response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseResponseError(f"Merge response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ParseResponseError(
            f"Merge response: expected dict, got {type(data).__name__}"
        )

    additions = data.get("additions", [])
    duplicates = data.get("duplicates", [])
    conflicts_raw = data.get("conflicts", [])
    affirmed_claim = data.get("affirmed_claim", "")

    if not isinstance(additions, list):
        additions = []
    if not isinstance(duplicates, list):
        duplicates = []
    if not isinstance(conflicts_raw, list):
        conflicts_raw = []

    conflicts = []
    for item in conflicts_raw:
        if isinstance(item, dict):
            existing_claim = str(item.get("existing_claim", ""))
            new_claim = str(item.get("new_claim", ""))
            if existing_claim and new_claim:
                conflicts.append(
                    ConflictPair(
                        existing_claim=existing_claim,
                        new_claim=new_claim,
                        existing_session_id=existing_session_id,
                        new_session_id=session_id,
                    )
                )

    return MergeResult(
        additions=[str(a) for a in additions if a],
        duplicates=[str(d) for d in duplicates if d],
        conflicts=conflicts,
        affirmed_claim=str(affirmed_claim) if affirmed_claim else "",
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
