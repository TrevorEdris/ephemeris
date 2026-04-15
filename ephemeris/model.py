"""model.py — ModelClient protocol and implementations.

Abstracts the model invocation layer so tests can use FakeModelClient
without importing the Anthropic SDK at all.

Public API:
    ConflictPair          — dataclass for a contradicting claim pair
    MergeResult           — dataclass for merge operation result
    ModelClient           — Protocol (structural typing, no inheritance required)
    AnthropicModelClient  — Production client; lazy-imports anthropic in __init__
    FakeModelClient       — Test double; returns a canned response

Environment:
    ANTHROPIC_API_KEY     — Required by AnthropicModelClient; raises ModelClientError if absent
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


_CITATION_RE = re.compile(r"^> Source:\s*\[[\d-]+\s+([^\]]+)\]\s*$", re.MULTILINE)


def _extract_latest_session_id(page_content: str) -> str:
    """Extract the most recent session ID from citation lines in a wiki page.

    Citation lines have the format:
        > Source: [YYYY-MM-DD session-id]

    Returns the last matching session ID, or "unknown" if none found.

    Args:
        page_content: Full text of a wiki page.

    Returns:
        Session ID string, or "unknown".
    """
    matches = _CITATION_RE.findall(page_content)
    return matches[-1] if matches else "unknown"


@dataclass
class ConflictPair:
    """A pair of contradicting claims between two sessions.

    Attributes:
        existing_claim: The claim already present in the wiki page.
        new_claim: The contradicting claim from the new session.
        existing_session_id: Session that produced the existing claim.
        new_session_id: Session that produced the new contradicting claim.
    """

    existing_claim: str
    new_claim: str
    existing_session_id: str
    new_session_id: str


@dataclass
class MergeResult:
    """Result of a merge_topic model call.

    Attributes:
        additions: Net-new claims/content to append to the existing page.
        duplicates: Claims already present in the page; discard.
        conflicts: Contradicting claim pairs to surface as inline conflict blocks.
        affirmed_claim: If the model resolved an existing conflict by affirming
                        one side, this holds the affirmed text. Empty string if
                        no resolution occurred.
    """

    additions: list[str]
    duplicates: list[str]
    conflicts: list[ConflictPair]
    affirmed_claim: str = ""


@runtime_checkable
class ModelClient(Protocol):
    """Protocol for model invocation.

    Any object with ``invoke`` and ``merge_topic`` methods satisfies this
    protocol — no inheritance required.
    """

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        """Invoke the model and return the response text.

        Args:
            system_prompt: System-level instructions (cached by Anthropic client).
            user_prompt: User message containing the transcript and task.

        Returns:
            Raw response text from the model.

        Raises:
            ModelClientError: If the invocation fails for any reason.
        """
        ...

    def merge_topic(self, existing: str, new: str, session_id: str) -> MergeResult:
        """Merge new session content into an existing wiki page.

        The model categorises each piece of new content as one of:
        - MERGE: net-new addition to append.
        - DUPLICATE: already present in existing content; discard.
        - CONFLICT: directly contradicts an existing claim; surface inline.

        Args:
            existing: Current content of the wiki page.
            new: New session content to integrate.
            session_id: Session identifier for the new content (for citation).

        Returns:
            MergeResult with additions, duplicates, and conflicts categorised.

        Raises:
            ModelClientError: If the invocation fails.
        """
        ...


class AnthropicModelClient:
    """Production model client backed by the Anthropic SDK.

    Lazy-imports the ``anthropic`` package inside ``__init__`` so that
    the module can be imported without the SDK installed (tests never
    instantiate this class).

    Uses prompt caching on the system prompt (``cache_control=ephemeral``)
    to reduce latency and cost on repeated invocations with a stable schema.

    Args:
        model: Anthropic model ID. Defaults to ``claude-sonnet-4-5``.

    Raises:
        ModelClientError: If ``ANTHROPIC_API_KEY`` is not set in the environment.
    """

    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        # Lazy import to keep tests fast and to avoid hard dep at import time
        import anthropic  # type: ignore[import]

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            from ephemeris.exceptions import ModelClientError
            raise ModelClientError("ANTHROPIC_API_KEY not set")

        self._client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY from env
        self._model = model

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        """Call the Anthropic API with prompt caching on the system prompt.

        Args:
            system_prompt: Stable schema+instructions block (cached).
            user_prompt: Per-transcript content (not cached).

        Returns:
            First text block from the model response.

        Raises:
            ModelClientError: On API error or empty response.
        """
        from ephemeris.exceptions import ModelClientError

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text  # type: ignore[union-attr]
        except Exception as exc:
            raise ModelClientError(f"Anthropic API call failed: {exc}") from exc

    def merge_topic(self, existing: str, new: str, session_id: str) -> "MergeResult":
        """Call the Anthropic API to merge new session content into existing page.

        Args:
            existing: Current wiki page content.
            new: New session content to integrate.
            session_id: New session identifier.

        Returns:
            MergeResult with additions, duplicates, and conflicts.

        Raises:
            ModelClientError: On API error or parse failure.
        """
        from ephemeris.exceptions import ModelClientError
        from ephemeris.prompts import (
            _MERGE_SYSTEM_PROMPT,
            build_merge_prompt,
            parse_merge_response,
        )

        user_prompt = build_merge_prompt(existing, new, session_id)
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": _MERGE_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text  # type: ignore[union-attr]
        except Exception as exc:
            raise ModelClientError(f"Anthropic merge API call failed: {exc}") from exc

        # Extract the existing session ID from the last citation in the page
        existing_session_id = _extract_latest_session_id(existing)
        return parse_merge_response(raw, session_id, existing_session_id=existing_session_id)


class FakeModelClient:
    """Test double for ModelClient.

    Returns pre-configured canned responses regardless of input.
    Never imports the ``anthropic`` package.

    Args:
        response: String to return from ``invoke``. Defaults to empty JSON
            operations list ``{"operations": []}``.
        merge_result: MergeResult to return from ``merge_topic``. Defaults to
            an empty MergeResult (no additions, no duplicates, no conflicts).
    """

    def __init__(
        self,
        response: str = '{"operations": []}',
        merge_result: Optional[MergeResult] = None,
    ) -> None:
        self._response = response
        self._merge_result = merge_result or MergeResult(
            additions=[], duplicates=[], conflicts=[]
        )

    def invoke(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        return self._response

    def merge_topic(  # noqa: ARG002
        self, existing: str, new: str, session_id: str
    ) -> MergeResult:
        return self._merge_result
