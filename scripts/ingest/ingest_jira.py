#!/usr/bin/env python3
"""Jira ticket enrichment for codebase-history ingest.

Called from ``ingest_codebase.py`` when a merge commit's PR body references
ticket keys. Can also be run standalone to enrich a list of keys.

Responsibilities:
    - Load / save the ``ingested-tickets.json`` state file.
    - Detect status deltas and emit delta episodes.
    - Recurse into epics and linked tickets (bounded depth).
    - Keep the ticket source pluggable via ``TICKET_SOURCE`` env var.

State is passed by reference into ``ingest_tickets`` rather than
loaded/saved per call — the caller loads once before the commit loop and
saves once at the end to avoid stale-read races on recursion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schema import CODEBASE_GROUP, EDGE_TYPES, ENTITY_TYPES_CODEBASE

from .ticket_sources import EpicEpisode, TicketEpisode, TicketSource

TICKET_STATE_FILENAME = "ingested-tickets.json"


# --- Pure helpers -----------------------------------------------------------


_JIRA_CODE_RE = re.compile(r"\{code(?::[^}]*)?\}(.*?)\{code\}", re.DOTALL)
_JIRA_QUOTE_RE = re.compile(r"\{quote\}(.*?)\{quote\}", re.DOTALL)
_JIRA_NOFORMAT_RE = re.compile(r"\{noformat\}(.*?)\{noformat\}", re.DOTALL)
_JIRA_HEADING_RE = re.compile(r"^h[1-6]\.\s*", re.MULTILINE)
_JIRA_BOLD_RE = re.compile(r"\*([^*\n]+)\*")
_JIRA_ITALIC_RE = re.compile(r"_([^_\n]+)_")
_JIRA_LINK_RE = re.compile(r"\[([^\]|]+)\|[^\]]+\]")
_JIRA_MENTION_RE = re.compile(r"\[~[^\]]+\]")


def strip_jira_markup(text: str | None) -> str:
    """Reduce Jira's wiki-style markup to plain prose.

    Not a complete renderer — just the high-frequency noise that would
    dilute LLM extraction. Code and noformat blocks are flattened to their
    inner text so code references survive.
    """
    if not text:
        return ""
    out = text
    out = _JIRA_CODE_RE.sub(lambda m: m.group(1), out)
    out = _JIRA_NOFORMAT_RE.sub(lambda m: m.group(1), out)
    out = _JIRA_QUOTE_RE.sub(lambda m: m.group(1), out)
    out = _JIRA_HEADING_RE.sub("", out)
    out = _JIRA_LINK_RE.sub(lambda m: m.group(1), out)
    out = _JIRA_MENTION_RE.sub("", out)
    out = _JIRA_BOLD_RE.sub(lambda m: m.group(1), out)
    out = _JIRA_ITALIC_RE.sub(lambda m: m.group(1), out)
    return out.strip()


def format_ticket_episode(ticket: TicketEpisode) -> str:
    parts: list[str] = [
        f"Type: {ticket.issue_type}",
        f"Summary: {ticket.summary}",
        f"Description: {strip_jira_markup(ticket.description)[:2000]}",
    ]
    if ticket.acceptance_criteria:
        parts.append(
            f"Acceptance criteria: {ticket.acceptance_criteria[:500]}"
        )
    if ticket.resolution:
        parts.append(
            f"Resolution: {ticket.resolution} — "
            f"{(ticket.resolution_description or '')[:500]}"
        )
    if ticket.comments:
        parts.append(f"Initial comment: {ticket.comments[0].body[:300]}")
        if len(ticket.comments) > 1:
            parts.append(f"Final comment: {ticket.comments[-1].body[:300]}")
    return "\n\n".join(p for p in parts if p)


def format_epic_episode(epic: EpicEpisode) -> str:
    return f"Epic: {epic.title}\n\nObjective: {epic.objective[:1000]}"


# --- State file -------------------------------------------------------------


def _state_dir() -> Path:
    override = os.environ.get("EPHEMERIS_STATE_ROOT")
    return Path(override) if override else Path.home() / ".ai" / "ephemeris" / "state"


def _state_path() -> Path:
    return _state_dir() / TICKET_STATE_FILENAME


def load_ticket_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        return {}
    return {}


def save_ticket_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str))


def needs_status_update(existing: dict[str, Any], new_status: str) -> bool:
    """Return True iff the stored status differs from ``new_status``."""
    return existing.get("status") != new_status


# --- Orchestration ----------------------------------------------------------


@dataclass
class _FakeEpisodeResult:
    """Structural match for ``add_episode`` return shape — used in tests."""

    episode: Any
    nodes: list = None  # type: ignore[assignment]
    edges: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.nodes is None:
            self.nodes = []
        if self.edges is None:
            self.edges = []


async def ingest_tickets(
    refs: list[str],
    parent_episode_uuid: str,
    state: dict[str, Any],
    *,
    ticket_source: TicketSource,
    graphiti: Any,
    depth: int = 0,
    max_depth: int = 1,
) -> None:
    """Ingest a list of ticket refs as episodes, bounded to ``max_depth``.

    New tickets produce a full episode and recurse into epics + linked
    tickets. Already-ingested tickets whose status has changed produce a
    delta episode. Everything else is a no-op.

    The caller owns ``state`` — load once before, save once after.
    """
    for key in refs:
        try:
            ticket = await ticket_source.get_ticket(key)
        except NotImplementedError:
            # Stub ticket source — skip, do not crash the whole ingest.
            continue

        if key not in state:
            body = format_ticket_episode(ticket)
            result = await graphiti.add_episode(
                name=f"Jira {key}: {ticket.summary}",
                episode_body=body,
                source_description="Jira",
                reference_time=ticket.created_at,
                group_id=CODEBASE_GROUP,
                entity_types=ENTITY_TYPES_CODEBASE,
                edge_types=EDGE_TYPES,
                previous_episode_uuids=[parent_episode_uuid],
            )
            ticket_uuid = str(result.episode.uuid)
            state[key] = {"uuid": ticket_uuid, "status": ticket.status}

            if ticket.epic_key and ticket.epic_key not in state:
                await ingest_epic(
                    ticket.epic_key,
                    ticket_uuid,
                    state,
                    ticket_source=ticket_source,
                    graphiti=graphiti,
                )

            if depth < max_depth:
                linked_keys = [
                    link.key
                    for link in ticket.issue_links[:5]
                    if link.key and link.key not in state
                ]
                if linked_keys:
                    await ingest_tickets(
                        linked_keys,
                        ticket_uuid,
                        state,
                        ticket_source=ticket_source,
                        graphiti=graphiti,
                        depth=depth + 1,
                        max_depth=max_depth,
                    )

        elif needs_status_update(state[key], ticket.status):
            prev_status = state[key].get("status", "unknown")
            body = (
                f"{key} transitioned from {prev_status} to {ticket.status}.\n"
                f"Resolution: {ticket.resolution or 'none'}\n"
                f"{ticket.resolution_description or ''}"
            )
            await graphiti.add_episode(
                name=f"Jira {key} status: {prev_status} → {ticket.status}",
                episode_body=body,
                source_description="Jira (status delta)",
                reference_time=datetime.now(timezone.utc),
                group_id=CODEBASE_GROUP,
                entity_types=ENTITY_TYPES_CODEBASE,
                edge_types=EDGE_TYPES,
                previous_episode_uuids=[state[key]["uuid"]],
            )
            state[key]["status"] = ticket.status


async def ingest_epic(
    epic_key: str,
    linked_from_uuid: str,
    state: dict[str, Any],
    *,
    ticket_source: TicketSource,
    graphiti: Any,
) -> None:
    try:
        epic = await ticket_source.get_epic(epic_key)
    except NotImplementedError:
        return
    result = await graphiti.add_episode(
        name=f"Epic {epic_key}: {epic.title}",
        episode_body=format_epic_episode(epic),
        source_description="Jira Epic",
        reference_time=epic.created_at,
        group_id=CODEBASE_GROUP,
        entity_types=ENTITY_TYPES_CODEBASE,
        edge_types=EDGE_TYPES,
        previous_episode_uuids=[linked_from_uuid],
    )
    state[epic_key] = {"uuid": str(result.episode.uuid), "status": "epic"}


# --- Ticket source factory -------------------------------------------------


def build_ticket_source() -> TicketSource:
    """Instantiate the configured ticket source (Jira by default)."""
    kind = os.environ.get("TICKET_SOURCE", "jira").lower()
    if kind == "jira":
        from .ticket_sources.jira import JiraClient  # noqa: PLC0415

        return JiraClient()
    if kind == "linear":
        from .ticket_sources.linear import LinearClient  # noqa: PLC0415

        return LinearClient()
    if kind == "github_issues":
        from .ticket_sources.github_issues import GitHubIssuesClient  # noqa: PLC0415

        return GitHubIssuesClient()
    raise ValueError(f"Unknown TICKET_SOURCE={kind}")


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "keys",
        nargs="+",
        help="Ticket keys to enrich (e.g. PROJ-123 INFRA-7)",
    )
    parser.add_argument(
        "--parent-episode-uuid",
        default="",
        help="UUID of the parent episode to link these tickets to",
    )
    parser.add_argument(
        "--max-depth", type=int, default=1, help="Recursion depth for linked tickets"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "keys": args.keys,
                    "parent_episode_uuid": args.parent_episode_uuid,
                    "max_depth": args.max_depth,
                },
                indent=2,
            )
        )
        return 0

    try:
        source = build_ticket_source()
    except Exception as e:  # noqa: BLE001
        print(f"error: ticket source init failed: {e}", file=sys.stderr)
        return 2

    from ingest.graphiti_client import get_graphiti  # noqa: PLC0415

    async def _run() -> None:
        graphiti = await get_graphiti()
        state = load_ticket_state()
        await ingest_tickets(
            args.keys,
            args.parent_episode_uuid,
            state,
            ticket_source=source,
            graphiti=graphiti,
            max_depth=args.max_depth,
        )
        save_ticket_state(state)

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
