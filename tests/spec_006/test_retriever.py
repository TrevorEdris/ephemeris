"""tests/spec_006/test_retriever.py — SPEC-006: Wiki Query.

Unit tests for FilesystemRetriever and pure functions.

Coverage:
    FilesystemRetriever: ranking, SCHEMA.md exclusion, empty wiki
    format_citations: pure function output format
    build_grounded_prompt: question placed after excerpts
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _write(root: Path, subpath: str, content: str) -> Path:
    p = root / subpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# FilesystemRetriever ranking
# ---------------------------------------------------------------------------

class TestFilesystemRetrieverRanksByTokenOverlap:
    """Retriever must rank pages by token overlap with the question, descending."""

    def test_ranks_highest_overlap_first(self, tmp_path):
        """Page with more matching tokens ranks above one with fewer."""
        from ephemeris.query import FilesystemRetriever

        _write(tmp_path, "topics/high.md",
               "# High\nRivendell valley elves Elrond Eriador location.\n")
        _write(tmp_path, "topics/low.md",
               "# Low\nA brief note about trees.\n")

        retriever = FilesystemRetriever(tmp_path)
        pages = retriever.retrieve("Rivendell valley elves Elrond location", top_n=5)

        assert len(pages) >= 1
        assert "high" in str(pages[0].path)

    def test_returns_at_most_top_n(self, tmp_path):
        """Retriever must return at most top_n pages."""
        from ephemeris.query import FilesystemRetriever

        for i in range(5):
            _write(tmp_path, f"topics/page{i}.md",
                   f"# Page {i}\nRivendell content {i}.\n")

        retriever = FilesystemRetriever(tmp_path)
        pages = retriever.retrieve("Rivendell", top_n=2)

        assert len(pages) <= 2

    def test_returns_only_pages_with_overlap(self, tmp_path):
        """Pages with zero token overlap must not be returned."""
        from ephemeris.query import FilesystemRetriever

        _write(tmp_path, "topics/relevant.md", "# Relevant\nRivendell elves.\n")
        _write(tmp_path, "topics/irrelevant.md", "# Irrelevant\nxyzzy quux baz.\n")

        retriever = FilesystemRetriever(tmp_path)
        pages = retriever.retrieve("Rivendell elves", top_n=5)

        paths = [str(p.path) for p in pages]
        assert not any("irrelevant" in p for p in paths)


# ---------------------------------------------------------------------------
# FilesystemRetriever: SCHEMA.md exclusion
# ---------------------------------------------------------------------------

class TestFilesystemRetrieverExcludesSchema:
    """SCHEMA.md must never appear in retrieval results."""

    def test_schema_md_excluded(self, tmp_path):
        """SCHEMA.md at wiki root must be excluded even when it matches."""
        from ephemeris.query import FilesystemRetriever

        _write(tmp_path, "SCHEMA.md",
               "# Schema\nRivendell elves Eriador valley topic entity decision.\n")
        _write(tmp_path, "topics/rivendell.md",
               "# Rivendell\nA valley.\n")

        retriever = FilesystemRetriever(tmp_path)
        pages = retriever.retrieve("Rivendell elves Eriador schema", top_n=5)

        paths = [str(p.path) for p in pages]
        assert not any("SCHEMA" in p for p in paths)

    def test_schema_md_excluded_when_only_match(self, tmp_path):
        """If SCHEMA.md is the only matching file, result is empty."""
        from ephemeris.query import FilesystemRetriever

        _write(tmp_path, "SCHEMA.md",
               "# Schema\nRivendell elves schema.\n")

        retriever = FilesystemRetriever(tmp_path)
        pages = retriever.retrieve("Rivendell elves schema", top_n=5)

        assert pages == []


# ---------------------------------------------------------------------------
# FilesystemRetriever: empty wiki
# ---------------------------------------------------------------------------

class TestFilesystemRetrieverEmptyWiki:
    """Empty wiki returns empty list."""

    def test_empty_wiki_returns_empty_list(self, tmp_path):
        """No .md files → retrieve returns []."""
        from ephemeris.query import FilesystemRetriever

        retriever = FilesystemRetriever(tmp_path)
        pages = retriever.retrieve("any question", top_n=5)

        assert pages == []


# ---------------------------------------------------------------------------
# format_citations pure function
# ---------------------------------------------------------------------------

class TestFormatCitations:
    """format_citations must return a markdown citations block."""

    def test_two_pages_produces_two_list_items(self, tmp_path):
        """Two WikiPage objects produce two markdown list items."""
        from ephemeris.query import WikiPage, format_citations

        pages = [
            WikiPage(path=Path("topics/rivendell.md"), title="Rivendell",
                     content="...", score=1.0),
            WikiPage(path=Path("entities/Elrond.md"), title="Elrond",
                     content="...", score=0.5),
        ]

        output = format_citations(pages)

        assert "Rivendell" in output
        assert "Elrond" in output
        # Each citation must be a markdown list item
        lines = [l for l in output.splitlines() if l.strip().startswith("- ")]
        assert len(lines) == 2

    def test_empty_list_returns_empty_or_blank(self):
        """format_citations([]) must return empty string or whitespace-only."""
        from ephemeris.query import format_citations

        output = format_citations([])

        assert output.strip() == ""


# ---------------------------------------------------------------------------
# build_grounded_prompt: question placed after excerpts
# ---------------------------------------------------------------------------

class TestBuildGroundedPrompt:
    """build_grounded_prompt structural tests."""

    def test_question_after_excerpts(self):
        """Question string must appear after the excerpt content in the prompt."""
        from ephemeris.query import WikiPage, build_grounded_prompt

        question = "Where is Rivendell?"
        pages = [
            WikiPage(path=Path("topics/rivendell.md"), title="Rivendell",
                     content="A valley in Eriador near the Misty Mountains.", score=1.0)
        ]

        prompt = build_grounded_prompt(question, pages)

        excerpt_idx = prompt.index("A valley in Eriador near the Misty Mountains.")
        question_idx = prompt.index(question)
        assert excerpt_idx < question_idx

    def test_grounding_instruction_present(self):
        """build_grounded_prompt must embed GROUNDING_INSTRUCTION."""
        from ephemeris.prompts import GROUNDING_INSTRUCTION
        from ephemeris.query import WikiPage, build_grounded_prompt

        pages = [
            WikiPage(path=Path("topics/foo.md"), title="Foo",
                     content="Some content.", score=1.0)
        ]

        prompt = build_grounded_prompt("What is foo?", pages)

        assert GROUNDING_INSTRUCTION in prompt

    def test_page_title_in_prompt(self):
        """Page title must appear in the assembled prompt."""
        from ephemeris.query import WikiPage, build_grounded_prompt

        pages = [
            WikiPage(path=Path("topics/rivendell.md"), title="Rivendell",
                     content="A valley.", score=1.0)
        ]

        prompt = build_grounded_prompt("Where is Rivendell?", pages)

        assert "Rivendell" in prompt
