"""test_ingest_skill_body.py — SPEC-010 static guard: skill body structure.

Parses commands/ingest.md frontmatter + body and asserts:
- Frontmatter has the exact required description, argument-hint, and allowed-tools.
- Body contains each required keyword / phrase from the Skill Contract.
- Body does NOT contain the SPEC-009 stub sentinel (replaced by this SPEC).
- Body contains zero occurrences of subprocess-style patterns or API key references.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
INGEST_MD = REPO_ROOT / "commands" / "ingest.md"

EXPECTED_DESCRIPTION = (
    "Ingest pending Claude Code sessions into the local wiki using the current session's model."
)
EXPECTED_ARGUMENT_HINT = '"[<session-id>]"'
EXPECTED_ALLOWED_TOOLS = ["Bash", "Read", "Write", "Glob"]

# Sentinel that MUST be absent after SPEC-010 lands
SPEC_009_STUB_SENTINEL = "full ingest implementation pending in SPEC-010"

# Strings forbidden everywhere in the body (P-1, P-2, P-3 compliance)
FORBIDDEN_STRINGS = [
    "python3 -m ephemeris",
    "anthropic",
    "ANTHROPIC_API_KEY",
    "ephemeris.cli",
]

# Required keywords from the Skill Contract body
REQUIRED_BODY_STRINGS = [
    "Resolve the schema",
    "Glob",
    "Read",
    "Write",
    "mv ",
    "$EPHEMERIS_SCHEMA_PATH",
    "schema.md",
    "SCHEMA.md",
    "default-schema.md",
    "$EPHEMERIS_STAGING_ROOT",
    "No pending sessions to ingest.",
    "No staged session matches",
    "session-end",
    "pre-compact",
    "processed/",
]


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
                pass
    if current_key and current_list:
        keys[current_key] = current_list
    return keys, body


class TestIngestSkillFrontmatter:
    def test_description_exact_match(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert fm.get("description") == EXPECTED_DESCRIPTION, (
            f"commands/ingest.md 'description' does not match expected value.\n"
            f"Expected: {EXPECTED_DESCRIPTION!r}\n"
            f"Got:      {fm.get('description')!r}"
        )

    def test_argument_hint(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        assert fm.get("argument-hint") == EXPECTED_ARGUMENT_HINT, (
            f"commands/ingest.md 'argument-hint' mismatch.\n"
            f"Expected: {EXPECTED_ARGUMENT_HINT!r}\n"
            f"Got:      {fm.get('argument-hint')!r}"
        )

    def test_allowed_tools_exact_set(self) -> None:
        text = INGEST_MD.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        tools = fm.get("allowed-tools")
        assert isinstance(tools, list), (
            "commands/ingest.md 'allowed-tools' must be a list"
        )
        assert sorted(tools) == sorted(EXPECTED_ALLOWED_TOOLS), (
            f"commands/ingest.md 'allowed-tools' mismatch.\n"
            f"Expected (sorted): {sorted(EXPECTED_ALLOWED_TOOLS)}\n"
            f"Got (sorted):      {sorted(tools)}"
        )


class TestIngestSkillBodyRequired:
    """Assert every required keyword / phrase from the Skill Contract is present."""

    def _body(self) -> str:
        text = INGEST_MD.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def test_resolve_the_schema(self) -> None:
        assert "Resolve the schema" in self._body()

    def test_glob_keyword(self) -> None:
        assert "Glob" in self._body()

    def test_read_keyword(self) -> None:
        assert "Read" in self._body()

    def test_write_keyword(self) -> None:
        assert "Write" in self._body()

    def test_bash_mv(self) -> None:
        assert "mv " in self._body()

    def test_schema_path_env_var(self) -> None:
        assert "$EPHEMERIS_SCHEMA_PATH" in self._body()

    def test_schema_md(self) -> None:
        assert "schema.md" in self._body()

    def test_schema_md_uppercase(self) -> None:
        assert "SCHEMA.md" in self._body()

    def test_default_schema_md(self) -> None:
        assert "default-schema.md" in self._body()

    def test_staging_root_env_var(self) -> None:
        assert "$EPHEMERIS_STAGING_ROOT" in self._body()

    def test_no_pending_sessions_message(self) -> None:
        assert "No pending sessions to ingest." in self._body()

    def test_no_staged_session_matches_message(self) -> None:
        assert "No staged session matches" in self._body()

    def test_session_end_hook_dir_reference(self) -> None:
        assert "session-end" in self._body()

    def test_pre_compact_hook_dir_reference(self) -> None:
        assert "pre-compact" in self._body()

    def test_processed_dir_reference(self) -> None:
        assert "processed/" in self._body()


class TestIngestSkillBodyAbsent:
    """Assert the SPEC-009 stub sentinel and forbidden patterns are absent."""

    def _body(self) -> str:
        text = INGEST_MD.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def test_stub_sentinel_absent(self) -> None:
        assert SPEC_009_STUB_SENTINEL not in self._body(), (
            "commands/ingest.md still contains the SPEC-009 stub sentinel — "
            "replace the body with the full Skill Contract."
        )

    def test_no_python3_subprocess(self) -> None:
        assert "python3 -m ephemeris" not in self._body(), (
            "commands/ingest.md contains a forbidden python3 subprocess pattern"
        )

    def test_no_anthropic_import(self) -> None:
        body_lower = self._body().lower()
        # Check case-insensitively for 'anthropic' as a word
        assert "anthropic" not in body_lower, (
            "commands/ingest.md contains 'anthropic' — violates P-1/P-2/P-3"
        )

    def test_no_api_key(self) -> None:
        assert "ANTHROPIC_API_KEY" not in self._body(), (
            "commands/ingest.md contains ANTHROPIC_API_KEY — violates P-2"
        )

    def test_no_ephemeris_cli(self) -> None:
        assert "ephemeris.cli" not in self._body(), (
            "commands/ingest.md contains ephemeris.cli — violates P-1"
        )
