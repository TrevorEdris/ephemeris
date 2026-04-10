"""GitHub Issues TicketSource (stub).

GitHub issue refs look like ``#<n>`` rather than the ``<PROJECT>-<N>`` shape
used by Jira/Linear. Ref extraction for this source lives in the caller
(``ingest_codebase.py``) under its own regex.

Left as a stub for the same reason as ``linear.py`` — the full GraphQL v4
mapping is P7c/P8 territory. Raises NotImplementedError when called.
"""

from __future__ import annotations

from .base import EpicEpisode, TicketEpisode


class GitHubIssuesClient:
    def __init__(self, token: str | None = None, repo: str | None = None) -> None:
        self.token = token
        self.repo = repo

    async def get_ticket(self, key: str) -> TicketEpisode:
        raise NotImplementedError(
            "GitHub Issues ticket source is not yet implemented. "
            "Use gh CLI via scripts/ingest/ingest_codebase.py for PR bodies "
            "in the meantime."
        )

    async def get_epic(self, key: str) -> EpicEpisode:
        raise NotImplementedError(
            "GitHub Issues does not have a native 'epic' concept."
        )
