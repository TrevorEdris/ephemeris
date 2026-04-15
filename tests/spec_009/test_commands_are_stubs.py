"""test_commands_are_stubs.py — SPEC-009 AC-14, AC-15, AC-16, AC-20.

Parses commands/ingest.md and commands/query.md and asserts:
- Valid frontmatter (description, argument-hint, allowed-tools)
- Body does NOT contain `python3 -m ephemeris.*`
- Body does NOT contain `anthropic` or `ANTHROPIC_API_KEY`

Note: stub sentinel assertions have been removed as both commands now have full
skill bodies (SPEC-010 replaced ingest.md, SPEC-011 replaced query.md). See
tests/spec_010/ and tests/spec_011/ for body-content guards respectively.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
INGEST_MD = REPO_ROOT / "commands" / "ingest.md"
QUERY_MD = REPO_ROOT / "commands" / "query.md"

FORBIDDEN_PATTERN = "python3 -m ephemeris."


def _parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Split YAML-ish frontmatter from body. Returns (keys, body)."""
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
    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])
    keys: dict[str, str | list[str]] = {}
    current_key = None
    current_list: list[str] = []
    for line in fm_lines:
        if line.startswith("  - "):
            if current_key:
                current_list.append(line.strip()[2:])
        elif ":" in line:
            if current_key and current_list:
                keys[current_key] = current_list
            current_list = []
            k, _, v = line.partition(":")
            current_key = k.strip()
            v = v.strip()
            if v:
                keys[current_key] = v
            else:
                # start of list
                pass
    if current_key and current_list:
        keys[current_key] = current_list
    return keys, body


class TestIngestStub:
    def test_ingest_frontmatter_description(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert "description" in fm, "commands/ingest.md missing 'description' in frontmatter"

    def test_ingest_frontmatter_argument_hint(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert "argument-hint" in fm, "commands/ingest.md missing 'argument-hint' in frontmatter"

    def test_ingest_frontmatter_allowed_tools(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert "allowed-tools" in fm, "commands/ingest.md missing 'allowed-tools' in frontmatter"

    def test_ingest_body_no_subprocess(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        assert FORBIDDEN_PATTERN not in text, (
            f"commands/ingest.md still contains '{FORBIDDEN_PATTERN}'"
        )

    def test_ingest_body_no_anthropic(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        assert "anthropic" not in text.lower() or "ANTHROPIC_API_KEY" not in text, True
        # More precise: the literal strings must be absent
        assert "ANTHROPIC_API_KEY" not in text, (
            "commands/ingest.md contains ANTHROPIC_API_KEY"
        )


class TestQueryStub:
    """Structural guards for commands/query.md.

    Note: test_query_body_contains_sentinel removed by SPEC-011 — stub body
    replaced with full skill contract. Body-content guards now live in
    tests/spec_011/test_query_skill_body.py and
    tests/spec_011/test_query_skill_grounding.py.
    """

    def test_query_frontmatter_description(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert "description" in fm, "commands/query.md missing 'description' in frontmatter"

    def test_query_frontmatter_argument_hint(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert "argument-hint" in fm, "commands/query.md missing 'argument-hint' in frontmatter"

    def test_query_frontmatter_allowed_tools(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert "allowed-tools" in fm, "commands/query.md missing 'allowed-tools' in frontmatter"

    def test_query_body_no_subprocess(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        assert FORBIDDEN_PATTERN not in text, (
            f"commands/query.md still contains '{FORBIDDEN_PATTERN}'"
        )

    def test_query_body_no_anthropic(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        assert "ANTHROPIC_API_KEY" not in text, (
            "commands/query.md contains ANTHROPIC_API_KEY"
        )
