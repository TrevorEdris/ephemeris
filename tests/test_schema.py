"""Tests for scripts/schema/entity_types.py — entity + edge contracts."""

from pydantic import BaseModel

from schema import (
    CODEBASE_GROUP,
    DOCS_GROUP,
    EDGE_TYPES,
    ENTITY_TYPES_CODEBASE,
    ENTITY_TYPES_WORKFLOW,
    WORKFLOW_GROUP,
    Decision,
    Epic,
    GitCommit,
    JiraTicket,
    Problem,
    Session,
    TechChoice,
)


def test_workflow_entities_contain_core_types():
    for name in ("Decision", "Problem", "TechChoice", "Session"):
        assert name in ENTITY_TYPES_WORKFLOW
        assert issubclass(ENTITY_TYPES_WORKFLOW[name], BaseModel)


def test_codebase_entities_contain_ticket_and_commit_types():
    for name in ("Decision", "Problem", "TechChoice", "JiraTicket", "Epic", "GitCommit"):
        assert name in ENTITY_TYPES_CODEBASE
        assert issubclass(ENTITY_TYPES_CODEBASE[name], BaseModel)


def test_edge_types_are_dict_of_basemodels():
    assert isinstance(EDGE_TYPES, dict)
    for name, cls in EDGE_TYPES.items():
        assert issubclass(cls, BaseModel), f"{name} is not a BaseModel subclass"
    for required in (
        "SupersedesEdge",
        "CausedByEdge",
        "ImplementsEdge",
        "PartOfEpicEdge",
        "BlocksEdge",
        "DuplicatesEdge",
    ):
        assert required in EDGE_TYPES


def test_decision_requires_what_and_why():
    d = Decision(what="use Kuzu", why="embedded, zero-server dev")
    assert d.what == "use Kuzu"
    assert d.why == "embedded, zero-server dev"
    assert d.alternatives == ""
    assert d.ticket is None


def test_problem_defaults():
    p = Problem(symptom="ingest fails on empty body")
    assert p.root_cause == ""
    assert p.resolution is None
    assert p.recurrence is False


def test_jira_ticket_fields():
    t = JiraTicket(key="PROJ-1", issue_type="Bug", summary="x")
    assert t.key == "PROJ-1"
    assert t.acceptance_criteria is None


def test_group_ids_distinct_and_stable():
    assert WORKFLOW_GROUP == "workflow-knowledge"
    assert CODEBASE_GROUP == "codebase-history"
    assert DOCS_GROUP == "codebase-docs"
    assert len({WORKFLOW_GROUP, CODEBASE_GROUP, DOCS_GROUP}) == 3


def test_unused_imports_are_importable():
    # Ensures they're re-exported from the package __init__
    _ = (TechChoice, Session, Epic, GitCommit)
