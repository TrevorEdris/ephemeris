"""model.py — ModelClient protocol and implementations.

Abstracts the model invocation layer so tests can use FakeModelClient
without importing the Anthropic SDK at all.

Public API:
    ModelClient           — Protocol (structural typing, no inheritance required)
    AnthropicModelClient  — Production client; lazy-imports anthropic in __init__
    FakeModelClient       — Test double; returns a canned response

Environment:
    ANTHROPIC_API_KEY     — Required by AnthropicModelClient; raises ModelClientError if absent
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


@runtime_checkable
class ModelClient(Protocol):
    """Protocol for model invocation.

    Any object with an ``invoke(system_prompt, user_prompt) -> str`` method
    satisfies this protocol — no inheritance required.
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


class FakeModelClient:
    """Test double for ModelClient.

    Returns a pre-configured canned response string regardless of input.
    Never imports the ``anthropic`` package.

    Args:
        response: String to return from ``invoke``. Defaults to empty JSON
            operations list ``{"operations": []}``.
    """

    def __init__(self, response: str = '{"operations": []}') -> None:
        self._response = response

    def invoke(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        return self._response
