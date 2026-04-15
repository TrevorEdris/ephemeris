"""test_prompts.py — Unit tests for ephemeris/prompts.py."""

from __future__ import annotations

import json

import pytest


def test_build_system_prompt_embeds_schema() -> None:
    """build_system_prompt includes the schema text in output."""
    from ephemeris.prompts import build_system_prompt

    schema = "## My Custom Schema\nTopics: kebab-case."
    prompt = build_system_prompt(schema)
    assert schema in prompt
    assert "operations" in prompt  # output format instructions present


def test_build_user_prompt_includes_session_metadata() -> None:
    """build_user_prompt includes session_id and session_date."""
    from ephemeris.prompts import build_user_prompt

    prompt = build_user_prompt(
        transcript_text="[USER] hello",
        session_id="my-session-001",
        session_date="2026-04-15",
    )
    assert "my-session-001" in prompt
    assert "2026-04-15" in prompt
    assert "[USER] hello" in prompt


def test_parse_response_valid_operations() -> None:
    """parse_response returns PageOperation list from valid JSON."""
    from ephemeris.prompts import PageOperation, parse_response

    raw = json.dumps({
        "operations": [
            {
                "action": "create",
                "page_type": "topic",
                "page_name": "test-topic",
                "content": {"overview": "A test.", "details": "More."},
                "cross_references": [],
            }
        ]
    })

    ops = parse_response(raw)
    assert len(ops) == 1
    assert ops[0].action == "create"
    assert ops[0].page_type == "topic"
    assert ops[0].page_name == "test-topic"
    assert ops[0].content["overview"] == "A test."


def test_parse_response_empty_operations() -> None:
    """parse_response returns empty list for {"operations": []}."""
    from ephemeris.prompts import parse_response

    ops = parse_response('{"operations": []}')
    assert ops == []


def test_parse_response_raises_on_invalid_json() -> None:
    """parse_response raises ParseResponseError on invalid JSON."""
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.prompts import parse_response

    with pytest.raises(ParseResponseError, match="not valid JSON"):
        parse_response("NOT JSON")


def test_parse_response_raises_on_empty_string() -> None:
    """parse_response raises ParseResponseError on empty string."""
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.prompts import parse_response

    with pytest.raises(ParseResponseError, match="empty response"):
        parse_response("")


def test_parse_response_raises_on_missing_operations_key() -> None:
    """parse_response raises ParseResponseError when 'operations' key absent."""
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.prompts import parse_response

    with pytest.raises(ParseResponseError, match="missing 'operations'"):
        parse_response('{"something": "else"}')


def test_parse_response_raises_on_invalid_action() -> None:
    """parse_response raises ParseResponseError for unknown action."""
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.prompts import parse_response

    raw = json.dumps({
        "operations": [
            {
                "action": "delete",  # invalid
                "page_type": "topic",
                "page_name": "foo",
                "content": {},
                "cross_references": [],
            }
        ]
    })

    with pytest.raises(ParseResponseError, match="invalid action"):
        parse_response(raw)


def test_parse_response_raises_on_invalid_page_type() -> None:
    """parse_response raises ParseResponseError for unknown page_type."""
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.prompts import parse_response

    raw = json.dumps({
        "operations": [
            {
                "action": "create",
                "page_type": "unknown_type",  # invalid
                "page_name": "foo",
                "content": {},
                "cross_references": [],
            }
        ]
    })

    with pytest.raises(ParseResponseError, match="invalid page_type"):
        parse_response(raw)
