"""Pydantic entity + edge types used across ephemeris ingest.

The schema is intentionally narrow for v1. Types like ``Person``, ``Team``,
``API``, ``Module``, and ``Dependency`` are omitted and should be added based
on extraction gaps observed during dog-fooding.

Graphiti requires entity_types / edge_types as ``dict[str, type[BaseModel]]``
(not bare sets). The ``ENTITY_TYPES_*`` and ``EDGE_TYPES`` dicts below are the
canonical forms passed to ``add_episode``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Entity Types ──────────────────────────────────────────────────


class Decision(BaseModel):
    """A choice made between alternatives, with rationale."""

    what: str = Field(..., description="What was decided.")
    why: str = Field(..., description="Rationale for the decision.")
    alternatives: str = Field(
        "", description="Options considered and rejected, comma-separated."
    )
    ticket: str | None = Field(
        None, description="Jira/Linear ref if applicable (e.g. PROJ-1234)."
    )


class Problem(BaseModel):
    """A bug, incident, or other issue encountered during work."""

    symptom: str = Field(..., description="Observable symptom.")
    root_cause: str = Field("", description="Confirmed root cause if known.")
    resolution: str | None = Field(None, description="How it was resolved.")
    recurrence: bool = Field(
        False, description="Whether this problem has happened before."
    )


class TechChoice(BaseModel):
    """A technology adopted, rejected, or evaluated."""

    technology: str = Field(..., description="Name of the technology.")
    context: str = Field("", description="Problem it solves.")
    tradeoffs: str = Field("", description="Known tradeoffs.")


class Session(BaseModel):
    """A work session captured under ~/src/.ai/sessions/."""

    ticket: str | None = Field(None, description="JIRA ref from session dir name.")
    slug: str = Field(..., description="Title slug from session dir name.")
    phase_reached: str = Field(
        "discover", description="discover | plan | implement"
    )


class JiraTicket(BaseModel):
    """A Jira (or Linear / GH Issues) ticket."""

    key: str = Field(..., description="e.g. PROJ-1234.")
    issue_type: str = Field("", description="Bug / Story / Task / Epic / etc.")
    summary: str = Field("", description="Ticket summary line.")
    problem_statement: str = Field(
        "", description="Trimmed description / problem statement."
    )
    acceptance_criteria: str | None = Field(None)
    resolution: str | None = Field(
        None, description="Done / Won't Fix / Duplicate / etc."
    )


class Epic(BaseModel):
    """A Jira epic grouping multiple tickets."""

    key: str = Field(..., description="Epic key (e.g. PROJ-1000).")
    title: str = Field("", description="Epic title.")
    objective: str = Field("", description="Trimmed objective / description.")


class GitCommit(BaseModel):
    """A merge commit (typically linked to a PR)."""

    sha: str = Field(..., description="Full SHA.")
    files_changed: str = Field(
        "", description="Comma-separated list of changed files (cap at 20)."
    )


# ── Edge Types ────────────────────────────────────────────────────


class SupersedesEdge(BaseModel):
    """A newer decision replaces an older one."""

    reason: str = Field("", description="Why the previous decision was superseded.")


class CausedByEdge(BaseModel):
    """A problem was caused by a specific change, commit, or decision."""

    evidence: str = Field("", description="Supporting evidence for causation.")


class ImplementsEdge(BaseModel):
    """A commit / PR implements a decision or ticket."""

    pr_number: str | None = Field(None)


class PartOfEpicEdge(BaseModel):
    """A ticket rolls up to an epic."""

    epic_key: str = Field(..., description="Parent epic key.")


class BlocksEdge(BaseModel):
    """One ticket blocks another."""


class DuplicatesEdge(BaseModel):
    """One ticket duplicates another."""


# ── Dict forms (Graphiti requires dict[str, type[BaseModel]], not bare sets) ──

ENTITY_TYPES_WORKFLOW: dict[str, type[BaseModel]] = {
    "Decision": Decision,
    "Problem": Problem,
    "TechChoice": TechChoice,
    "Session": Session,
}

ENTITY_TYPES_CODEBASE: dict[str, type[BaseModel]] = {
    "Decision": Decision,
    "Problem": Problem,
    "TechChoice": TechChoice,
    "JiraTicket": JiraTicket,
    "Epic": Epic,
    "GitCommit": GitCommit,
}

EDGE_TYPES: dict[str, type[BaseModel]] = {
    "SupersedesEdge": SupersedesEdge,
    "CausedByEdge": CausedByEdge,
    "ImplementsEdge": ImplementsEdge,
    "PartOfEpicEdge": PartOfEpicEdge,
    "BlocksEdge": BlocksEdge,
    "DuplicatesEdge": DuplicatesEdge,
}

# ── Group IDs ─────────────────────────────────────────────────────

WORKFLOW_GROUP = "workflow-knowledge"  # session artifacts
CODEBASE_GROUP = "codebase-history"  # git / PRs / tickets
DOCS_GROUP = "codebase-docs"  # READMEs, ADRs, runbooks
