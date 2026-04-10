"""TicketSource — pluggable ticket-backend interface.

Implementations live alongside this file: ``jira.py`` (REST v3), ``linear.py``
(GraphQL), ``github_issues.py`` (REST/GraphQL). All three return the same
``TicketEpisode`` / ``EpicEpisode`` dataclasses so the downstream ingest
path is source-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class TicketComment:
    author: str
    body: str
    created_at: datetime


@dataclass
class IssueLink:
    key: str
    relation: str  # "blocks", "relates to", "duplicates", ...


@dataclass
class TicketEpisode:
    key: str
    issue_type: str
    summary: str
    description: str
    status: str
    created_at: datetime
    acceptance_criteria: str | None = None
    resolution: str | None = None
    resolution_description: str | None = None
    epic_key: str | None = None
    comments: list[TicketComment] = field(default_factory=list)
    issue_links: list[IssueLink] = field(default_factory=list)


@dataclass
class EpicEpisode:
    key: str
    title: str
    objective: str
    created_at: datetime


@runtime_checkable
class TicketSource(Protocol):
    """Backend for resolving ticket keys to structured episodes."""

    async def get_ticket(self, key: str) -> TicketEpisode: ...

    async def get_epic(self, key: str) -> EpicEpisode: ...
