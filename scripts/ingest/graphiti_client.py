"""Shared Graphiti client setup.

Single place to construct a ``Graphiti`` instance wired to Kuzu (the default
embedded backend). Overriding the DB path via ``EPHEMERIS_DB_PATH`` keeps tests
and one-off experiments from clobbering the default graph.

KuzuDriver's parameter is ``db`` (not ``db_path``) and defaults to ``:memory:``
when omitted. ``os.path.expanduser`` is required because Kuzu will not expand
``~`` on its own.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".ai" / "ephemeris" / "db"
STATE_DIR = Path.home() / ".ai" / "ephemeris" / "state"


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


async def get_graphiti(db: str | None = None):
    """Construct a Graphiti instance with Kuzu backend.

    Deferred imports: graphiti-core is a heavy dep pulling in LLM clients.
    Importing at module load time would make ``--dry-run`` / ``--estimate``
    modes require the full dep, which defeats their purpose.
    """
    from graphiti_core import Graphiti  # noqa: PLC0415
    from graphiti_core.driver.kuzu_driver import KuzuDriver  # noqa: PLC0415

    db_path = db if db is not None else default_db_path()
    driver = KuzuDriver(db=db_path)
    return Graphiti(driver)
