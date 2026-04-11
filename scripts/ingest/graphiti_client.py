"""Shared Graphiti client setup.

Single place to construct a ``Graphiti`` instance wired to Kuzu (the default
embedded backend). Overriding the DB path via ``EPHEMERIS_DB_PATH`` keeps tests
and one-off experiments from clobbering the default graph.

KuzuDriver's parameter is ``db`` (not ``db_path``) and defaults to ``:memory:``
when omitted. ``os.path.expanduser`` is required because Kuzu will not expand
``~`` on its own.

LLM client selection policy (see ``llm_client_kind``):

    1. ``EPHEMERIS_LLM_PROVIDER=anthropic|openai`` wins if set
    2. else ``ANTHROPIC_API_KEY`` set → anthropic (user opt-in signal)
    3. else → openai (the historical default)

Embeddings are a separate question. Graphiti's default embedder is OpenAI,
so anthropic-for-reasoning users still need ``OPENAI_API_KEY`` unless they
swap the embedder (see docs/setup.md for the Ollama + sentence-transformers
fully-local path).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

LlmKind = Literal["anthropic", "openai"]

DEFAULT_DB_PATH = Path.home() / ".ai" / "ephemeris" / "db"
STATE_DIR = Path.home() / ".ai" / "ephemeris" / "state"

_SUPPORTED_PROVIDERS: tuple[LlmKind, ...] = ("anthropic", "openai")


def default_db_path() -> str:
    """Return the Kuzu DB path, honoring ``EPHEMERIS_DB_PATH`` override."""
    override = os.environ.get("EPHEMERIS_DB_PATH")
    if override:
        return os.path.expanduser(override)
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return str(DEFAULT_DB_PATH)


def ensure_state_dir() -> Path:
    """Create ``~/.ai/ephemeris/state/`` if it doesn't exist; return the path."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def llm_client_kind() -> LlmKind:
    """Return which LLM client graphiti should use for reasoning.

    Pure function — reads env vars, no side effects, no graphiti imports.
    Tested directly; the client construction path in ``get_graphiti`` is
    the only thing that turns this string into a real client.
    """
    explicit = os.environ.get("EPHEMERIS_LLM_PROVIDER")
    if explicit:
        normalized = explicit.strip().lower()
        if normalized not in _SUPPORTED_PROVIDERS:
            raise ValueError(
                f"EPHEMERIS_LLM_PROVIDER={explicit!r} is not one of "
                f"{_SUPPORTED_PROVIDERS}"
            )
        return normalized  # type: ignore[return-value]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"


async def get_graphiti(db: str | None = None):
    """Construct a Graphiti instance with Kuzu backend.

    Deferred imports: graphiti-core is a heavy dep pulling in LLM clients.
    Importing at module load time would make ``--dry-run`` / ``--estimate``
    modes require the full dep, which defeats their purpose.

    LLM client is picked by ``llm_client_kind``. Embedder is left at the
    graphiti default (OpenAI) since Anthropic does not offer embeddings —
    see module docstring for the full story.
    """
    from graphiti_core import Graphiti  # noqa: PLC0415
    from graphiti_core.driver.kuzu_driver import KuzuDriver  # noqa: PLC0415

    db_path = db if db is not None else default_db_path()
    driver = KuzuDriver(db=db_path)

    kind = llm_client_kind()
    if kind == "anthropic":
        # Deferred — graphiti-core only installs AnthropicClient when
        # the ``[anthropic]`` extra is present. Raise a helpful error if
        # the user set ANTHROPIC_API_KEY without installing the extra.
        try:
            from graphiti_core.llm_client.anthropic_client import (  # noqa: PLC0415
                AnthropicClient,
            )
        except ImportError as e:
            raise ImportError(
                "ANTHROPIC_API_KEY is set but graphiti-core was installed "
                "without the [anthropic] extra. Run "
                "`pip install 'graphiti-core[anthropic]'` or unset "
                "ANTHROPIC_API_KEY to fall back to OpenAI."
            ) from e
        return Graphiti(driver, llm_client=AnthropicClient())

    return Graphiti(driver)
