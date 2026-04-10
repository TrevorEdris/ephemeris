"""Tests for scripts/ingest/ingest_jira.py — pure helpers + orchestration.

Real Jira HTTP, real graphiti writes, and the real state dir are never
touched. Tests inject a fake TicketSource and a fake graphiti-shaped
object, and monkeypatch EPHEMERIS_STATE_ROOT so load/save round-trips
land in tmp_path.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from ingest import ingest_jira as ij
from ingest.ticket_sources import (
    EpicEpisode,
    IssueLink,
    TicketComment,
    TicketEpisode,
)


# --- strip_jira_markup ------------------------------------------------------


def test_strip_jira_markup_handles_none_and_empty():
    assert ij.strip_jira_markup(None) == ""
    assert ij.strip_jira_markup("") == ""


def test_strip_jira_markup_flattens_code_block():
    assert ij.strip_jira_markup("{code}print('hi'){code}") == "print('hi')"


def test_strip_jira_markup_flattens_code_block_with_language():
    assert (
        ij.strip_jira_markup("{code:python}x = 1{code}")
        == "x = 1"
    )


def test_strip_jira_markup_flattens_noformat_and_quote():
    assert ij.strip_jira_markup("{noformat}raw text{noformat}") == "raw text"
    assert ij.strip_jira_markup("{quote}said it{quote}") == "said it"


def test_strip_jira_markup_strips_headings():
    assert ij.strip_jira_markup("h1. Title\nbody") == "Title\nbody"
    assert ij.strip_jira_markup("h3. Section") == "Section"


def test_strip_jira_markup_strips_emphasis():
    assert ij.strip_jira_markup("*bold* and _italic_") == "bold and italic"


def test_strip_jira_markup_flattens_links_and_mentions():
    assert (
        ij.strip_jira_markup("See [docs|https://example.com] for [~alice]")
        == "See docs for"
    )


# --- format_ticket_episode --------------------------------------------------


def _make_ticket(**overrides) -> TicketEpisode:
    defaults = dict(
        key="PROJ-1",
        issue_type="Story",
        summary="Do the thing",
        description="h1. Overview\nbuild it",
        status="In Progress",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        acceptance_criteria="Thing must work",
        resolution=None,
        resolution_description=None,
        epic_key=None,
        comments=[],
        issue_links=[],
    )
    defaults.update(overrides)
    return TicketEpisode(**defaults)


def test_format_ticket_episode_includes_type_summary_description():
    body = ij.format_ticket_episode(_make_ticket())
    assert "Type: Story" in body
    assert "Summary: Do the thing" in body
    # h1. stripped, prose preserved
    assert "Overview" in body
    assert "build it" in body
    # Jira heading marker removed
    assert "h1." not in body


def test_format_ticket_episode_includes_acceptance_criteria_when_present():
    body = ij.format_ticket_episode(_make_ticket())
    assert "Acceptance criteria: Thing must work" in body


def test_format_ticket_episode_omits_empty_sections():
    body = ij.format_ticket_episode(
        _make_ticket(acceptance_criteria=None, resolution=None, comments=[])
    )
    assert "Acceptance criteria" not in body
    assert "Resolution" not in body
    assert "Initial comment" not in body


def test_format_ticket_episode_includes_resolution_when_present():
    ticket = _make_ticket(
        resolution="Fixed",
        resolution_description="Shipped in 1.2.3",
    )
    body = ij.format_ticket_episode(ticket)
    assert "Resolution: Fixed" in body
    assert "Shipped in 1.2.3" in body


def test_format_ticket_episode_includes_first_and_last_comment():
    t = _make_ticket(
        comments=[
            TicketComment("alice", "first thoughts", datetime(2026, 1, 2, tzinfo=timezone.utc)),
            TicketComment("bob", "middle", datetime(2026, 1, 3, tzinfo=timezone.utc)),
            TicketComment("carol", "wrapping up", datetime(2026, 1, 4, tzinfo=timezone.utc)),
        ]
    )
    body = ij.format_ticket_episode(t)
    assert "first thoughts" in body
    assert "wrapping up" in body
    # middle comment should NOT appear — only first + last
    assert "middle" not in body


def test_format_ticket_episode_single_comment_no_final():
    t = _make_ticket(
        comments=[
            TicketComment("alice", "only one", datetime(2026, 1, 2, tzinfo=timezone.utc)),
        ]
    )
    body = ij.format_ticket_episode(t)
    assert "Initial comment: only one" in body
    assert "Final comment" not in body


def test_format_ticket_episode_truncates_long_description():
    t = _make_ticket(description="x" * 5000)
    body = ij.format_ticket_episode(t)
    # description capped at 2000
    assert body.count("x") <= 2000


# --- format_epic_episode ----------------------------------------------------


def test_format_epic_episode_shape():
    epic = EpicEpisode(
        key="PROJ-100",
        title="Q1 Platform",
        objective="Make the platform faster",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    body = ij.format_epic_episode(epic)
    assert body.startswith("Epic: Q1 Platform")
    assert "Make the platform faster" in body


# --- state file I/O ---------------------------------------------------------


@pytest.fixture
def state_root(monkeypatch, tmp_path):
    monkeypatch.setenv("EPHEMERIS_STATE_ROOT", str(tmp_path))
    return tmp_path


def test_load_ticket_state_missing_file_returns_empty(state_root):
    assert ij.load_ticket_state() == {}


def test_save_then_load_roundtrips(state_root):
    ij.save_ticket_state({"PROJ-1": {"uuid": "abc", "status": "Done"}})
    loaded = ij.load_ticket_state()
    assert loaded == {"PROJ-1": {"uuid": "abc", "status": "Done"}}


def test_load_ticket_state_ignores_corrupt_file(state_root):
    (state_root / ij.TICKET_STATE_FILENAME).write_text("{not json")
    assert ij.load_ticket_state() == {}


def test_load_ticket_state_ignores_non_dict(state_root):
    (state_root / ij.TICKET_STATE_FILENAME).write_text("[]")
    assert ij.load_ticket_state() == {}


def test_save_creates_parent_directory(monkeypatch, tmp_path):
    nested = tmp_path / "deep" / "nest"
    monkeypatch.setenv("EPHEMERIS_STATE_ROOT", str(nested))
    ij.save_ticket_state({"X-1": {"uuid": "u", "status": "s"}})
    assert (nested / ij.TICKET_STATE_FILENAME).exists()


# --- needs_status_update ----------------------------------------------------


def test_needs_status_update_true_when_differs():
    assert ij.needs_status_update({"status": "Open"}, "Done") is True


def test_needs_status_update_false_when_same():
    assert ij.needs_status_update({"status": "Done"}, "Done") is False


def test_needs_status_update_true_when_missing():
    assert ij.needs_status_update({}, "Done") is True


# --- ingest_tickets orchestration ------------------------------------------


class _FakeEpisode:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class _FakeResult:
    def __init__(self, uuid: str) -> None:
        self.episode = _FakeEpisode(uuid)
        self.nodes: list = []
        self.edges: list = []


class FakeGraphiti:
    """Records add_episode calls; hands back unique episode uuids."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._counter = 0

    async def add_episode(self, **kwargs):
        self._counter += 1
        uuid = f"ep-{self._counter}"
        self.calls.append({"uuid": uuid, **kwargs})
        return _FakeResult(uuid)


class FakeTicketSource:
    """In-memory TicketSource. Tests pre-populate `tickets` and `epics`."""

    def __init__(self) -> None:
        self.tickets: dict[str, TicketEpisode] = {}
        self.epics: dict[str, EpicEpisode] = {}

    async def get_ticket(self, key: str) -> TicketEpisode:
        if key not in self.tickets:
            raise KeyError(key)
        return self.tickets[key]

    async def get_epic(self, key: str) -> EpicEpisode:
        if key not in self.epics:
            raise KeyError(key)
        return self.epics[key]


class StubTicketSource:
    """Raises NotImplementedError for every call — mimics the linear/gh stubs."""

    async def get_ticket(self, key: str) -> TicketEpisode:
        raise NotImplementedError("stub")

    async def get_epic(self, key: str) -> EpicEpisode:
        raise NotImplementedError("stub")


def test_ingest_tickets_creates_new_episode_and_updates_state():
    src = FakeTicketSource()
    src.tickets["PROJ-1"] = _make_ticket()
    g = FakeGraphiti()
    state: dict = {}

    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1"],
            parent_episode_uuid="parent-uuid",
            state=state,
            ticket_source=src,
            graphiti=g,
        )
    )

    assert "PROJ-1" in state
    assert state["PROJ-1"]["status"] == "In Progress"
    assert state["PROJ-1"]["uuid"] == "ep-1"
    assert len(g.calls) == 1
    call = g.calls[0]
    assert call["name"].startswith("Jira PROJ-1")
    assert call["source_description"] == "Jira"
    assert call["previous_episode_uuids"] == ["parent-uuid"]


def test_ingest_tickets_skips_already_ingested_when_status_unchanged():
    src = FakeTicketSource()
    src.tickets["PROJ-1"] = _make_ticket(status="Done")
    g = FakeGraphiti()
    state = {"PROJ-1": {"uuid": "old-uuid", "status": "Done"}}

    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1"],
            parent_episode_uuid="parent",
            state=state,
            ticket_source=src,
            graphiti=g,
        )
    )

    assert g.calls == []
    assert state["PROJ-1"]["uuid"] == "old-uuid"


def test_ingest_tickets_emits_delta_on_status_change():
    src = FakeTicketSource()
    src.tickets["PROJ-1"] = _make_ticket(
        status="Done",
        resolution="Fixed",
        resolution_description="Shipped",
    )
    g = FakeGraphiti()
    state = {"PROJ-1": {"uuid": "old-uuid", "status": "In Progress"}}

    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1"],
            parent_episode_uuid="parent",
            state=state,
            ticket_source=src,
            graphiti=g,
        )
    )

    assert len(g.calls) == 1
    call = g.calls[0]
    assert "status" in call["name"]
    assert "In Progress" in call["name"]
    assert "Done" in call["name"]
    assert call["source_description"] == "Jira (status delta)"
    assert call["previous_episode_uuids"] == ["old-uuid"]
    assert state["PROJ-1"]["status"] == "Done"
    # uuid pointer should NOT change — delta links back to the full episode
    assert state["PROJ-1"]["uuid"] == "old-uuid"


def test_ingest_tickets_recurses_into_epic():
    src = FakeTicketSource()
    src.tickets["PROJ-1"] = _make_ticket(epic_key="PROJ-100")
    src.epics["PROJ-100"] = EpicEpisode(
        key="PROJ-100",
        title="Platform",
        objective="Be fast",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    g = FakeGraphiti()
    state: dict = {}

    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1"],
            parent_episode_uuid="parent",
            state=state,
            ticket_source=src,
            graphiti=g,
        )
    )

    assert "PROJ-100" in state
    assert state["PROJ-100"]["status"] == "epic"
    # first call is the ticket, second is the epic
    assert len(g.calls) == 2
    assert g.calls[1]["name"].startswith("Epic PROJ-100")
    assert g.calls[1]["previous_episode_uuids"] == ["ep-1"]


def test_ingest_tickets_recurses_into_linked_tickets_bounded():
    src = FakeTicketSource()
    src.tickets["PROJ-1"] = _make_ticket(
        key="PROJ-1",
        issue_links=[IssueLink(key="PROJ-2", relation="blocks")],
    )
    # PROJ-2 also has a link — should NOT recurse past max_depth=1
    src.tickets["PROJ-2"] = _make_ticket(
        key="PROJ-2",
        issue_links=[IssueLink(key="PROJ-3", relation="blocks")],
    )
    src.tickets["PROJ-3"] = _make_ticket(key="PROJ-3")
    g = FakeGraphiti()
    state: dict = {}

    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1"],
            parent_episode_uuid="parent",
            state=state,
            ticket_source=src,
            graphiti=g,
            max_depth=1,
        )
    )

    assert "PROJ-1" in state
    assert "PROJ-2" in state
    assert "PROJ-3" not in state  # depth bound enforced


def test_ingest_tickets_silently_skips_notimplemented_source():
    g = FakeGraphiti()
    state: dict = {}
    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1", "PROJ-2"],
            parent_episode_uuid="parent",
            state=state,
            ticket_source=StubTicketSource(),
            graphiti=g,
        )
    )
    assert state == {}
    assert g.calls == []


def test_ingest_tickets_does_not_double_ingest_linked_already_in_state():
    src = FakeTicketSource()
    src.tickets["PROJ-1"] = _make_ticket(
        key="PROJ-1",
        issue_links=[IssueLink(key="PROJ-2", relation="blocks")],
    )
    src.tickets["PROJ-2"] = _make_ticket(key="PROJ-2")
    g = FakeGraphiti()
    # PROJ-2 already known
    state = {"PROJ-2": {"uuid": "pre-existing", "status": "In Progress"}}

    asyncio.run(
        ij.ingest_tickets(
            ["PROJ-1"],
            parent_episode_uuid="parent",
            state=state,
            ticket_source=src,
            graphiti=g,
        )
    )

    assert "PROJ-1" in state
    # Only PROJ-1 should have been written; PROJ-2 already in state
    assert len(g.calls) == 1
    assert g.calls[0]["name"].startswith("Jira PROJ-1")


# --- build_ticket_source ----------------------------------------------------


def test_build_ticket_source_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("TICKET_SOURCE", "bogus")
    with pytest.raises(ValueError, match="bogus"):
        ij.build_ticket_source()


def test_build_ticket_source_linear_stub(monkeypatch):
    monkeypatch.setenv("TICKET_SOURCE", "linear")
    src = ij.build_ticket_source()
    assert src.__class__.__name__ == "LinearClient"


def test_build_ticket_source_github_issues_stub(monkeypatch):
    monkeypatch.setenv("TICKET_SOURCE", "github_issues")
    src = ij.build_ticket_source()
    assert src.__class__.__name__ == "GitHubIssuesClient"


# --- CLI dry-run ------------------------------------------------------------


def test_cli_dry_run_emits_json(capsys):
    rc = ij.main(
        [
            "PROJ-1",
            "PROJ-2",
            "--parent-episode-uuid",
            "parent-uuid",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload == {
        "dry_run": True,
        "keys": ["PROJ-1", "PROJ-2"],
        "parent_episode_uuid": "parent-uuid",
        "max_depth": 1,
    }
