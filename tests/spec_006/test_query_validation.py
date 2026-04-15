"""tests/spec_006/test_query_validation.py — SPEC-006: Wiki Query.

Tests for input validation (AC-6), empty wiki (AC-3), no-match gate (AC-2).
All tests use FakeModelClient; no Anthropic SDK imports.

AC coverage:
    AC-2 (no matching pages → cannot answer, no model call)
    AC-3 (empty wiki → explicit message, no model call)
    AC-6 (empty/whitespace question → usage error, no I/O)
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers — counting retriever and counting model client
# ---------------------------------------------------------------------------

class _CountingRetriever:
    """Retriever that records call count and returns configurable pages."""

    def __init__(self, pages=None):
        self.call_count = 0
        self._pages = pages or []

    def retrieve(self, question: str, top_n: int = 5):
        self.call_count += 1
        return self._pages


class _CountingModelClient:
    """Model double that counts answer_query calls."""

    def __init__(self, answer: str = "model answer"):
        self.call_count = 0
        self._answer = answer

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return ""

    def merge_topic(self, existing: str, new: str, session_id: str):
        from ephemeris.model import MergeResult
        return MergeResult(additions=[], duplicates=[], conflicts=[])

    def answer_query(self, prompt: str) -> str:
        self.call_count += 1
        return self._answer


# ---------------------------------------------------------------------------
# AC-6: empty / whitespace question → usage error, no I/O
# ---------------------------------------------------------------------------

class TestQueryEmptyQuestion:
    """AC-6: empty or whitespace question returns usage error without I/O."""

    def test_empty_string_returns_usage_error(self, tmp_path):
        """run_query('') must return usage_error=True without touching retriever or model."""
        from ephemeris.query import run_query

        retriever = _CountingRetriever()
        model = _CountingModelClient()

        result = run_query("", wiki_root=tmp_path, model_client=model, retriever=retriever)

        assert result.usage_error is True
        assert retriever.call_count == 0
        assert model.call_count == 0

    def test_whitespace_only_returns_usage_error(self, tmp_path):
        """run_query('   ') must return usage_error=True."""
        from ephemeris.query import run_query

        retriever = _CountingRetriever()
        model = _CountingModelClient()

        result = run_query("   \t\n", wiki_root=tmp_path, model_client=model, retriever=retriever)

        assert result.usage_error is True
        assert retriever.call_count == 0
        assert model.call_count == 0

    def test_main_empty_question_exits_nonzero(self, tmp_path):
        """main(['']) must exit non-zero."""
        from ephemeris.query import main

        exit_code = main(["--wiki-root", str(tmp_path), ""])

        assert exit_code != 0

    def test_main_whitespace_question_exits_nonzero(self, tmp_path):
        """main(['   ']) must exit non-zero."""
        from ephemeris.query import main

        exit_code = main(["--wiki-root", str(tmp_path), "   "])

        assert exit_code != 0


# ---------------------------------------------------------------------------
# AC-3: empty wiki → explicit "wiki is empty" message, no model call
# ---------------------------------------------------------------------------

class TestQueryEmptyWiki:
    """AC-3: wiki with no pages → explicit message, no model call."""

    def test_empty_wiki_returns_empty_wiki_flag(self, tmp_path):
        """run_query on empty tmp_path returns empty_wiki=True."""
        from ephemeris.query import run_query

        model = _CountingModelClient()

        result = run_query("Where is Rivendell?", wiki_root=tmp_path, model_client=model)

        assert result.empty_wiki is True
        assert model.call_count == 0

    def test_empty_wiki_no_model_call(self, tmp_path):
        """empty wiki must not invoke the model."""
        from ephemeris.query import run_query

        model = _CountingModelClient()
        run_query("any question", wiki_root=tmp_path, model_client=model)

        assert model.call_count == 0

    def test_main_empty_wiki_prints_wiki_is_empty(self, tmp_path, capsys):
        """main with empty wiki prints 'wiki is empty' to stdout."""
        from ephemeris.query import main

        main(["--wiki-root", str(tmp_path), "Where is Rivendell?"])

        out = capsys.readouterr().out
        assert "wiki is empty" in out.lower()

    def test_main_empty_wiki_exits_zero(self, tmp_path):
        """empty wiki is not an error — exit 0."""
        from ephemeris.query import main

        exit_code = main(["--wiki-root", str(tmp_path), "Where is Rivendell?"])

        assert exit_code == 0


# ---------------------------------------------------------------------------
# AC-2: populated wiki with no relevant pages → "cannot answer", no model call
# ---------------------------------------------------------------------------

class TestQueryNoMatchingPages:
    """AC-2: populated wiki, zero relevance to question → cannot answer."""

    def _make_wiki(self, wiki_root: Path) -> None:
        """Populate wiki with a page about elves."""
        topics = wiki_root / "topics"
        topics.mkdir(parents=True, exist_ok=True)
        (topics / "elves.md").write_text(
            "# Elves\n\nElves are immortal beings from Middle-earth.\n",
            encoding="utf-8",
        )

    def test_no_match_returns_no_match_flag(self, tmp_path):
        """Question about submarines against an elves-only wiki returns no_match=True."""
        from ephemeris.query import run_query

        self._make_wiki(tmp_path)
        model = _CountingModelClient()

        result = run_query("How do submarines work?", wiki_root=tmp_path, model_client=model)

        assert result.no_match is True
        assert model.call_count == 0

    def test_no_match_no_model_call(self, tmp_path):
        """no-match gate must prevent model invocation."""
        from ephemeris.query import run_query

        self._make_wiki(tmp_path)
        model = _CountingModelClient()
        run_query("How do submarines work?", wiki_root=tmp_path, model_client=model)

        assert model.call_count == 0

    def test_main_no_match_prints_cannot_answer(self, tmp_path, capsys):
        """main with no-match wiki prints 'cannot answer' to stdout."""
        from ephemeris.query import main

        self._make_wiki(tmp_path)
        main(["--wiki-root", str(tmp_path), "How do submarines work?"])

        out = capsys.readouterr().out
        assert "cannot answer" in out.lower()

    def test_main_no_match_exits_zero(self, tmp_path):
        """no-match is not an error — exit 0."""
        from ephemeris.query import main

        self._make_wiki(tmp_path)
        exit_code = main(["--wiki-root", str(tmp_path), "How do submarines work?"])

        assert exit_code == 0


# ---------------------------------------------------------------------------
# MAJOR: gate paths must never construct AnthropicModelClient
# ---------------------------------------------------------------------------

class TestGatePathsNoModelClient:
    """Verify AnthropicModelClient is never constructed on gate-exit paths.

    Uses monkeypatch-bomb: AnthropicModelClient.__init__ raises a distinctive
    RuntimeError so any accidental construction fails the test loudly.
    """

    def _make_wiki(self, wiki_root: Path) -> None:
        """Populate wiki with a page about elves (for no-match gate)."""
        topics = wiki_root / "topics"
        topics.mkdir(parents=True, exist_ok=True)
        (topics / "elves.md").write_text(
            "# Elves\n\nElves are immortal beings from Middle-earth.\n",
            encoding="utf-8",
        )

    def test_main_empty_wiki_constructs_no_model_client(
        self, monkeypatch, tmp_path, capsys
    ):
        """Empty-wiki gate exits before AnthropicModelClient is ever constructed."""
        import ephemeris.model as model_mod
        from ephemeris.query import main

        def _boom(*args, **kwargs):
            raise RuntimeError(
                "AnthropicModelClient must not be constructed on gate paths"
            )

        monkeypatch.setattr(model_mod.AnthropicModelClient, "__init__", _boom)
        monkeypatch.delenv("EPHEMERIS_MODEL_CLIENT", raising=False)

        exit_code = main(["--wiki-root", str(tmp_path), "Where is Rivendell?"])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "wiki is empty" in captured.out.lower()

    def test_main_no_match_constructs_no_model_client(
        self, monkeypatch, tmp_path, capsys
    ):
        """No-match gate exits before AnthropicModelClient is ever constructed."""
        import ephemeris.model as model_mod
        from ephemeris.query import main

        def _boom(*args, **kwargs):
            raise RuntimeError(
                "AnthropicModelClient must not be constructed on gate paths"
            )

        monkeypatch.setattr(model_mod.AnthropicModelClient, "__init__", _boom)
        monkeypatch.delenv("EPHEMERIS_MODEL_CLIENT", raising=False)
        self._make_wiki(tmp_path)

        exit_code = main(["--wiki-root", str(tmp_path), "How do submarines work?"])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "cannot answer" in captured.out.lower()

    def test_main_empty_question_constructs_no_model_client(
        self, monkeypatch, tmp_path
    ):
        """Empty-question gate exits before AnthropicModelClient is ever constructed."""
        import ephemeris.model as model_mod
        from ephemeris.query import main

        def _boom(*args, **kwargs):
            raise RuntimeError(
                "AnthropicModelClient must not be constructed on gate paths"
            )

        monkeypatch.setattr(model_mod.AnthropicModelClient, "__init__", _boom)
        monkeypatch.delenv("EPHEMERIS_MODEL_CLIENT", raising=False)

        exit_code = main(["--wiki-root", str(tmp_path), ""])

        assert exit_code != 0
