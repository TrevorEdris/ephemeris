"""Linear GraphQL TicketSource (stub).

Linear uses the same ``<PROJECT>-<N>`` key shape as Jira, so the
disambiguation happens via the ``TICKET_SOURCE`` env var at
``ingest_jira.py`` boot time, not at regex level.

Left as a stub — the full GraphQL schema mapping is out of scope for P7b.
Raises ``NotImplementedError`` so a misconfigured ``TICKET_SOURCE=linear``
fails loudly instead of silently returning empty tickets.
"""

from __future__ import annotations

from .base import EpicEpisode, TicketEpisode


class LinearClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def get_ticket(self, key: str) -> TicketEpisode:
        raise NotImplementedError(
            "Linear ticket source is not yet implemented. "
            "Contributions welcome — see scripts/ingest/ticket_sources/jira.py "
            "for the reference shape."
        )

    async def get_epic(self, key: str) -> EpicEpisode:
        raise NotImplementedError(
            "Linear epic source is not yet implemented."
        )
