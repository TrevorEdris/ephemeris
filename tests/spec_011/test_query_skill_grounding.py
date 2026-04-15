"""test_query_skill_grounding.py — SPEC-011 grounding rule and sentinel string guards.

Asserts:
- Body contains a grounding-rule phrase ("only from the content" or "traceable to").
- Body contains all three sentinel strings verbatim.
- Body contains the missing-wiki sentinel prefix "Wiki not found at".
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
QUERY_MD = REPO_ROOT / "commands" / "query.md"

SENTINEL_USAGE = 'Usage: /ephemeris:query "<question>"'
SENTINEL_EMPTY_WIKI = "Wiki is empty — no pages have been built yet."
SENTINEL_CANNOT_ANSWER = "Cannot answer this from the wiki — no relevant pages found."
SENTINEL_WIKI_NOT_FOUND_PREFIX = "Wiki not found at"


def _parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Split YAML-ish frontmatter from body. Returns (keys_dict, body_str)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    body = "\n".join(lines[end + 1:])
    return {}, body


class TestQueryGrounding:
    def test_grounding_rule_present(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        has_grounding = (
            "only from the content" in body
            or "traceable to" in body
        )
        assert has_grounding, (
            "commands/query.md body missing grounding rule phrase.\n"
            "Expected one of: 'only from the content' or 'traceable to'"
        )

    def test_sentinel_usage(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert SENTINEL_USAGE in body, (
            f"commands/query.md body missing usage sentinel.\n"
            f"Expected verbatim: {SENTINEL_USAGE!r}"
        )

    def test_sentinel_empty_wiki(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert SENTINEL_EMPTY_WIKI in body, (
            f"commands/query.md body missing empty-wiki sentinel.\n"
            f"Expected verbatim: {SENTINEL_EMPTY_WIKI!r}"
        )

    def test_sentinel_cannot_answer(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert SENTINEL_CANNOT_ANSWER in body, (
            f"commands/query.md body missing cannot-answer sentinel.\n"
            f"Expected verbatim: {SENTINEL_CANNOT_ANSWER!r}"
        )

    def test_sentinel_wiki_not_found_prefix(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert SENTINEL_WIKI_NOT_FOUND_PREFIX in body, (
            f"commands/query.md body missing missing-wiki sentinel prefix.\n"
            f"Expected: body to contain {SENTINEL_WIKI_NOT_FOUND_PREFIX!r}"
        )
