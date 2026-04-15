"""tests/spec_006/test_query_pipeline.py — SPEC-006: Wiki Query.

Tests for the full synthesis pipeline and retriever unit tests.

AC coverage:
    AC-1  (single match → answer + citation)
    AC-4  (partial coverage — grounding-instruction contract, documented)
    AC-5  (multiple matches → all cited)
    AC-7  (prompt contains grounding instruction verbatim)
    AC-8  (citations always include every retrieved page — documented)
    AC-9  (retrieval error surfaced, no partial answer)
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ScriptableModelClient:
    """Model double that records the last prompt and returns a scripted answer."""

    def __init__(self, answer: str = "The answer."):
        self._answer = answer
        self.last_prompt: str | None = None
        self.call_count = 0

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return ""

    def merge_topic(self, existing: str, new: str, session_id: str):
        from ephemeris.model import MergeResult
        return MergeResult(additions=[], duplicates=[], conflicts=[])

    def answer_query(self, prompt: str) -> str:
        self.last_prompt = prompt
        self.call_count += 1
        return self._answer


class _ErrorRetriever:
    """Retriever that always raises."""

    def retrieve(self, question: str, top_n: int = 5):
        raise RuntimeError("index read failure")


def _write_page(wiki_root: Path, subdir: str, filename: str, content: str) -> Path:
    d = wiki_root / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# AC-1: single match → answer + citation
# ---------------------------------------------------------------------------

class TestQuerySingleMatch:
    """AC-1: populated wiki, single relevant page → answer with citation."""

    def test_answer_contains_model_response(self, tmp_path, capsys):
        """The synthesized answer must include the model's response text."""
        from ephemeris.query import run_query

        _write_page(
            tmp_path, "topics", "rivendell.md",
            "# Rivendell\n\nRivendell is located in the Misty Mountains.\n",
        )
        model = _ScriptableModelClient(answer="Rivendell is in the Misty Mountains.")

        result = run_query(
            "Where is Rivendell?",
            wiki_root=tmp_path,
            model_client=model,
        )

        assert "Rivendell is in the Misty Mountains." in result.answer

    def test_citation_contains_page_path(self, tmp_path):
        """Citations must reference the retrieved page."""
        from ephemeris.query import run_query

        _write_page(
            tmp_path, "topics", "rivendell.md",
            "# Rivendell\n\nRivendell is located in the Misty Mountains.\n",
        )
        model = _ScriptableModelClient(answer="Rivendell is in the Misty Mountains.")

        result = run_query(
            "Where is Rivendell?",
            wiki_root=tmp_path,
            model_client=model,
        )

        paths = [str(page.path) for page in result.citations]
        assert any("rivendell" in p for p in paths)

    def test_prompt_contains_page_content(self, tmp_path):
        """The prompt passed to the model must include the page text."""
        from ephemeris.query import run_query

        _write_page(
            tmp_path, "topics", "rivendell.md",
            "# Rivendell\n\nRivendell is located in the Misty Mountains.\n",
        )
        model = _ScriptableModelClient()

        run_query("Where is Rivendell?", wiki_root=tmp_path, model_client=model)

        assert model.last_prompt is not None
        assert "Rivendell" in model.last_prompt


# ---------------------------------------------------------------------------
# AC-5: multiple matches → all cited
# ---------------------------------------------------------------------------

class TestQueryMultipleMatches:
    """AC-5: all retrieved pages appear in citations regardless of model output."""

    def test_all_three_pages_cited(self, tmp_path):
        """Citations include every retrieved page, not just the top one."""
        from ephemeris.query import run_query

        _write_page(tmp_path, "topics", "elrond.md",
                    "# Elrond\n\nElrond is the lord of Rivendell.\n")
        _write_page(tmp_path, "topics", "rivendell.md",
                    "# Rivendell\n\nRivendell is a valley in Eriador.\n")
        _write_page(tmp_path, "topics", "elves.md",
                    "# Elves\n\nElves are immortal beings of Rivendell.\n")

        model = _ScriptableModelClient(answer="The elves of Rivendell are led by Elrond.")

        result = run_query(
            "Tell me about Rivendell elves Elrond",
            wiki_root=tmp_path,
            model_client=model,
            top_n=3,
        )

        cited_paths = [str(p.path) for p in result.citations]
        assert any("elrond" in p for p in cited_paths)
        assert any("rivendell" in p for p in cited_paths)
        assert any("elves" in p for p in cited_paths)


# ---------------------------------------------------------------------------
# AC-7: prompt contains grounding instruction verbatim
# ---------------------------------------------------------------------------

class TestQueryGroundingInstruction:
    """AC-7: the grounding instruction literal is verifiable from the prompt string."""

    def test_prompt_contains_grounding_instruction(self, tmp_path):
        """Prompt must contain GROUNDING_INSTRUCTION verbatim."""
        from ephemeris.prompts import GROUNDING_INSTRUCTION
        from ephemeris.query import run_query

        _write_page(tmp_path, "topics", "rivendell.md",
                    "# Rivendell\n\nA valley in Eriador.\n")
        model = _ScriptableModelClient()

        run_query("Where is Rivendell?", wiki_root=tmp_path, model_client=model)

        assert model.last_prompt is not None
        assert GROUNDING_INSTRUCTION in model.last_prompt

    def test_question_placed_after_excerpts(self, tmp_path):
        """The question string must appear after the excerpts block in the prompt.

        Spec explicitly requires this to reduce prior-knowledge leakage.
        """
        from ephemeris.query import build_grounded_prompt, WikiPage

        question = "Where is Rivendell?"
        pages = [
            WikiPage(
                path=Path("topics/rivendell.md"),
                title="Rivendell",
                content="A valley in Eriador.",
                score=1.0,
            )
        ]

        prompt = build_grounded_prompt(question, pages)

        # The excerpt content must appear before the question in the prompt
        excerpt_idx = prompt.index("A valley in Eriador.")
        question_idx = prompt.index(question)
        assert excerpt_idx < question_idx, (
            "Question must appear AFTER excerpts to reduce prior-knowledge leakage"
        )


# ---------------------------------------------------------------------------
# AC-4: partial coverage — grounding-instruction enforces the gap surfacing
# ---------------------------------------------------------------------------

class TestQueryPartialCoverage:
    """AC-4: gap between question and wiki content is surfaced by the model.

    The grounding instruction tells the model to say "I cannot answer this
    from the wiki." when excerpts are insufficient. Host code does NOT
    post-process the model response — the instruction IS the enforcement.
    This test verifies the grounding instruction is in the prompt, which
    covers AC-4 by the prompt-contract interpretation documented in the brief.
    """

    def test_grounding_instruction_present_for_partial_match(self, tmp_path):
        """Grounding instruction must be in the prompt even for partial coverage."""
        from ephemeris.prompts import GROUNDING_INSTRUCTION
        from ephemeris.query import run_query

        # A page about elves that only partly answers a question about elvish music
        _write_page(tmp_path, "topics", "elves.md",
                    "# Elves\n\nElves are immortal beings of Middle-earth.\n")
        model = _ScriptableModelClient(answer="The wiki mentions elves but not their music.")

        run_query("What music do elves play?", wiki_root=tmp_path, model_client=model)

        assert model.last_prompt is not None
        assert GROUNDING_INSTRUCTION in model.last_prompt


# ---------------------------------------------------------------------------
# AC-8: answer traceable to cited pages (prompt-contract test)
# ---------------------------------------------------------------------------

class TestQueryAnswerTraceable:
    """AC-8: every factual claim is traceable to a cited page.

    This is enforced structurally:
    1. The grounding instruction tells the model to use only provided excerpts.
    2. Citations are appended by host code, not generated by the model — they
       always reflect every page actually retrieved (tested by AC-5 test above).
    This test documents the contract and verifies both structural constraints.
    """

    def test_citations_include_all_retrieved_pages(self, tmp_path):
        """Every page passed to the model appears in citations."""
        from ephemeris.query import run_query

        _write_page(tmp_path, "topics", "shire.md",
                    "# The Shire\n\nThe Shire is a peaceful region of Middle-earth.\n")
        model = _ScriptableModelClient(answer="The Shire is peaceful.")

        result = run_query("Tell me about the Shire", wiki_root=tmp_path, model_client=model)

        # All pages in result.citations must have been retrieved
        # (host code appends ALL retrieved pages, not just ones mentioned by model)
        assert len(result.citations) >= 1
        cited_paths = [str(p.path) for p in result.citations]
        assert any("shire" in p for p in cited_paths)

    def test_grounding_instruction_enforces_traceability(self, tmp_path):
        """GROUNDING_INSTRUCTION in the prompt is the traceability contract."""
        from ephemeris.prompts import GROUNDING_INSTRUCTION
        from ephemeris.query import run_query

        _write_page(tmp_path, "topics", "shire.md",
                    "# The Shire\n\nThe Shire is a peaceful region.\n")
        model = _ScriptableModelClient()

        run_query("Tell me about the Shire", wiki_root=tmp_path, model_client=model)

        assert GROUNDING_INSTRUCTION in model.last_prompt


# ---------------------------------------------------------------------------
# AC-9: retrieval error → surfaced to stderr, no partial answer
# ---------------------------------------------------------------------------

class TestQueryRetrievalError:
    """AC-9: retrieval error surfaces cleanly with no partial answer."""

    def test_retrieval_error_returns_retrieval_error_field(self, tmp_path):
        """QueryResult.retrieval_error must be set when retriever raises."""
        from ephemeris.query import run_query

        _write_page(tmp_path, "topics", "rivendell.md",
                    "# Rivendell\n\nA valley in Eriador.\n")
        model = _ScriptableModelClient()

        result = run_query(
            "Where is Rivendell?",
            wiki_root=tmp_path,
            model_client=model,
            retriever=_ErrorRetriever(),
        )

        assert result.retrieval_error is not None
        assert "index read failure" in result.retrieval_error

    def test_retrieval_error_no_model_call(self, tmp_path):
        """Retrieval error must abort before the model is called."""
        from ephemeris.query import run_query

        _write_page(tmp_path, "topics", "rivendell.md",
                    "# Rivendell\n\nA valley in Eriador.\n")
        model = _ScriptableModelClient()

        run_query(
            "Where is Rivendell?",
            wiki_root=tmp_path,
            model_client=model,
            retriever=_ErrorRetriever(),
        )

        assert model.call_count == 0

    def test_main_retrieval_error_exits_nonzero(self, tmp_path, monkeypatch):
        """CLI exits non-zero when retrieval raises."""
        import ephemeris.query as query_mod

        _write_page(tmp_path, "topics", "rivendell.md",
                    "# Rivendell\n\nA valley in Eriador.\n")

        # Monkeypatch FilesystemRetriever to raise on retrieve
        original_cls = query_mod.FilesystemRetriever

        class _BrokenRetriever:
            def __init__(self, wiki_root):
                pass
            def retrieve(self, question, top_n=5):
                raise RuntimeError("index read failure")

        monkeypatch.setattr(query_mod, "FilesystemRetriever", _BrokenRetriever)

        exit_code = query_mod.main(["--wiki-root", str(tmp_path), "Where is Rivendell?"])

        assert exit_code != 0
