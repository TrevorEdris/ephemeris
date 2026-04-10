"""Jira REST v3 TicketSource.

Config via environment:
    JIRA_BASE_URL   e.g. https://your-org.atlassian.net
    JIRA_EMAIL      basic-auth email
    JIRA_API_TOKEN  basic-auth API token (NOT password)

The client uses stdlib ``urllib`` so the ingest script has no extra deps.
Network calls are deferred inside the async methods; instantiating this
class is cheap and does not hit the network.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from .base import EpicEpisode, IssueLink, TicketComment, TicketEpisode


class JiraConfigError(RuntimeError):
    pass


class JiraClient:
    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")
        if not (self.base_url and self.email and self.api_token):
            raise JiraConfigError(
                "Jira not configured — set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN."
            )
        creds = base64.b64encode(
            f"{self.email}:{self.api_token}".encode()
        ).decode()
        self._auth_header = f"Basic {creds}"

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read().decode())

    async def get_ticket(self, key: str) -> TicketEpisode:
        data = self._get(f"/rest/api/3/issue/{key}?expand=names,renderedFields")
        fields = data.get("fields", {})
        return TicketEpisode(
            key=key,
            issue_type=fields.get("issuetype", {}).get("name", "Task"),
            summary=fields.get("summary", ""),
            description=_render_adf(fields.get("description")) or "",
            status=fields.get("status", {}).get("name", "Unknown"),
            created_at=_parse_jira_date(fields.get("created")),
            acceptance_criteria=fields.get("customfield_acceptance_criteria"),
            resolution=(fields.get("resolution") or {}).get("name"),
            resolution_description=fields.get("resolutiondescription"),
            epic_key=fields.get("customfield_epic_link"),
            comments=[
                TicketComment(
                    author=c.get("author", {}).get("displayName", "unknown"),
                    body=_render_adf(c.get("body")) or "",
                    created_at=_parse_jira_date(c.get("created")),
                )
                for c in (fields.get("comment", {}) or {}).get("comments", [])
            ],
            issue_links=[
                IssueLink(
                    key=(
                        link.get("inwardIssue", link.get("outwardIssue", {}))
                    ).get("key", ""),
                    relation=(link.get("type") or {}).get("name", ""),
                )
                for link in fields.get("issuelinks", [])
                if link.get("inwardIssue") or link.get("outwardIssue")
            ],
        )

    async def get_epic(self, key: str) -> EpicEpisode:
        data = self._get(f"/rest/api/3/issue/{key}")
        fields = data.get("fields", {})
        return EpicEpisode(
            key=key,
            title=fields.get("summary", ""),
            objective=_render_adf(fields.get("description")) or "",
            created_at=_parse_jira_date(fields.get("created")),
        )


def _parse_jira_date(value: str | None) -> datetime:
    if not value:
        return datetime.min
    # Jira returns ISO-8601 with milliseconds and a trailing +0000 offset.
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.min


def _render_adf(node: Any) -> str:
    """Best-effort flatten of Atlassian Document Format to plain text.

    Only extracts ``text`` leaves — enough for episode body signal.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "text" in node:
            return node["text"]
        children = node.get("content", [])
        return "".join(_render_adf(c) for c in children)
    if isinstance(node, list):
        return "".join(_render_adf(c) for c in node)
    return ""
