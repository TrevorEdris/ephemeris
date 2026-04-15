"""test_query_skill_body.py — SPEC-011 static guard tests for commands/query.md.

Asserts:
- Frontmatter has correct description, argument-hint, allowed-tools (Read/Glob/Grep only).
- Body contains required instruction landmarks.
- SPEC-009 stub sentinel is ABSENT.
- Forbidden symbols (subprocess calls, anthropic refs, Write/Edit/Bash tool names) are ABSENT.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
QUERY_MD = REPO_ROOT / "commands" / "query.md"

EXPECTED_DESCRIPTION = (
    "Answer a question from the local wiki using the current session's model. Read-only."
)
EXPECTED_ARGUMENT_HINT = '"<question>"'
EXPECTED_ALLOWED_TOOLS = {"Read", "Glob", "Grep"}

SPEC_009_STUB_SENTINEL = (
    "full query implementation pending in SPEC-011"
)

REQUIRED_BODY_SUBSTRINGS = [
    "Resolve the wiki root",
    "Glob",
    "Grep",
    "Read",
    "Sources",
    "Cannot answer",
    "Usage:",
    "$EPHEMERIS_WIKI_ROOT",
]

# These must not appear anywhere in the body (checked lowercase where appropriate)
FORBIDDEN_EXACT = [
    "python3 -m ephemeris",
    "anthropic",
    "ANTHROPIC_API_KEY",
    "ephemeris.cli",
]

# Tool names that must NOT appear as tool invocations in the skill body.
# Write and Edit are straight forbidden. Bash is forbidden (narrowed palette).
FORBIDDEN_TOOLS = ["Write", "Edit", "Bash"]


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
    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])
    keys: dict[str, str | list[str]] = {}
    current_key: str | None = None
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
                pass  # start of list
    if current_key and current_list:
        keys[current_key] = current_list
    return keys, body


class TestQueryFrontmatter:
    def test_description_exact(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert fm.get("description") == EXPECTED_DESCRIPTION, (
            f"commands/query.md description mismatch.\n"
            f"Expected: {EXPECTED_DESCRIPTION!r}\n"
            f"Got:      {fm.get('description')!r}"
        )

    def test_argument_hint(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert fm.get("argument-hint") == EXPECTED_ARGUMENT_HINT, (
            f"commands/query.md argument-hint mismatch.\n"
            f"Expected: {EXPECTED_ARGUMENT_HINT!r}\n"
            f"Got:      {fm.get('argument-hint')!r}"
        )

    def test_allowed_tools_exact_set(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        tools = fm.get("allowed-tools")
        assert isinstance(tools, list), (
            "commands/query.md allowed-tools must be a list"
        )
        actual = set(tools)
        assert actual == EXPECTED_ALLOWED_TOOLS, (
            f"commands/query.md allowed-tools must be exactly {EXPECTED_ALLOWED_TOOLS}.\n"
            f"Got: {actual}"
        )

    def test_allowed_tools_no_bash(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        tools = fm.get("allowed-tools", [])
        assert "Bash" not in tools, "commands/query.md allowed-tools must NOT include Bash"

    def test_allowed_tools_no_write(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        tools = fm.get("allowed-tools", [])
        assert "Write" not in tools, "commands/query.md allowed-tools must NOT include Write"

    def test_allowed_tools_no_edit(self) -> None:
        text = QUERY_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        tools = fm.get("allowed-tools", [])
        assert "Edit" not in tools, "commands/query.md allowed-tools must NOT include Edit"


class TestQueryBody:
    def test_stub_sentinel_absent(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert SPEC_009_STUB_SENTINEL not in body, (
            f"commands/query.md still contains the SPEC-009 stub sentinel.\n"
            f"Sentinel: {SPEC_009_STUB_SENTINEL!r}\n"
            "Replace the stub body with the full SPEC-011 skill contract."
        )

    def test_contains_resolve_wiki_root(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Resolve the wiki root" in body, (
            "commands/query.md body missing 'Resolve the wiki root'"
        )

    def test_contains_glob(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Glob" in body, "commands/query.md body missing 'Glob'"

    def test_contains_grep(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Grep" in body, "commands/query.md body missing 'Grep'"

    def test_contains_read(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Read" in body, "commands/query.md body missing 'Read'"

    def test_contains_sources(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Sources" in body, "commands/query.md body missing 'Sources'"

    def test_contains_cannot_answer(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Cannot answer" in body, "commands/query.md body missing 'Cannot answer'"

    def test_contains_usage(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Usage:" in body, "commands/query.md body missing 'Usage:'"

    def test_contains_ephemeris_wiki_root_env_var(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "$EPHEMERIS_WIKI_ROOT" in body, (
            "commands/query.md body missing '$EPHEMERIS_WIKI_ROOT'"
        )

    def test_no_subprocess_call(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "python3 -m ephemeris" not in body, (
            "commands/query.md body contains forbidden subprocess call 'python3 -m ephemeris'"
        )

    def test_no_anthropic_reference(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "anthropic" not in body.lower(), (
            "commands/query.md body contains forbidden reference to 'anthropic'"
        )

    def test_no_anthropic_api_key(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "ANTHROPIC_API_KEY" not in body, (
            "commands/query.md body contains ANTHROPIC_API_KEY"
        )

    def test_no_ephemeris_cli_reference(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "ephemeris.cli" not in body, (
            "commands/query.md body contains 'ephemeris.cli'"
        )

    def test_no_write_tool(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Write" not in body, (
            "commands/query.md body contains forbidden tool 'Write'"
        )

    def test_no_edit_tool(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Edit" not in body, (
            "commands/query.md body contains forbidden tool 'Edit'"
        )

    def test_no_bash_tool(self) -> None:
        _, body = _parse_frontmatter(QUERY_MD.read_text(encoding="utf-8"))
        assert "Bash" not in body, (
            "commands/query.md body contains forbidden tool 'Bash' (narrowed palette: Read/Glob/Grep only)"
        )
