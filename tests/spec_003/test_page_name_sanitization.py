"""test_page_name_sanitization.py — SPEC-003 path traversal prevention tests.

Verifies that _sanitize_page_name rejects names that could escape the wiki root
and that write_page uses it on all routing branches.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ephemeris.exceptions import WikiWriteError
from ephemeris.wiki import _sanitize_page_name


class TestRejectBadPageNames:
    def test_reject_parent_directory_escape(self) -> None:
        with pytest.raises(WikiWriteError, match="forbidden token"):
            _sanitize_page_name("../../evil")

    def test_reject_absolute_path(self) -> None:
        with pytest.raises(WikiWriteError):
            _sanitize_page_name("/etc/passwd")

    def test_reject_embedded_separator(self) -> None:
        with pytest.raises(WikiWriteError, match="forbidden token"):
            _sanitize_page_name("topics/evil")

    def test_reject_null_byte(self) -> None:
        with pytest.raises(WikiWriteError, match="forbidden token"):
            _sanitize_page_name("evil\x00.md")

    def test_reject_empty_name(self) -> None:
        with pytest.raises(WikiWriteError, match="empty"):
            _sanitize_page_name("")

    def test_reject_whitespace_only(self) -> None:
        with pytest.raises(WikiWriteError, match="empty"):
            _sanitize_page_name("   ")


class TestAcceptNormalName:
    def test_accept_normal_name(self, tmp_path: Path) -> None:
        result = _sanitize_page_name("the-shire")
        assert result == "the-shire"

    def test_write_page_topic_uses_sanitized_name(self, tmp_path: Path) -> None:
        """write_page raises WikiWriteError for traversal attempts on topic."""
        from ephemeris.wiki import write_page

        op = MagicMock()
        op.page_type = "topic"
        op.page_name = "../../evil"
        op.content = {}
        op.cross_references = []

        with pytest.raises(WikiWriteError):
            write_page(op, tmp_path, "> Source: [test]")

    def test_write_page_entity_uses_sanitized_name(self, tmp_path: Path) -> None:
        """write_page raises WikiWriteError for traversal attempts on entity."""
        from ephemeris.wiki import write_page

        op = MagicMock()
        op.page_type = "entity"
        op.page_name = "../../../etc/passwd"
        op.content = {}
        op.cross_references = []

        with pytest.raises(WikiWriteError):
            write_page(op, tmp_path, "> Source: [test]")

    def test_write_page_decision_uses_sanitized_name(self, tmp_path: Path) -> None:
        """append_to_decisions raises WikiWriteError for traversal attempts."""
        from ephemeris.wiki import write_page

        op = MagicMock()
        op.page_type = "decision"
        op.page_name = "../../evil"
        op.content = {}
        op.cross_references = []

        with pytest.raises(WikiWriteError):
            write_page(op, tmp_path, "> Source: [test]")

    def test_accept_normal_name_writes_correct_path(self, tmp_path: Path) -> None:
        """Normal page name writes under topics/ inside wiki_root."""
        from ephemeris.wiki import write_page

        op = MagicMock()
        op.page_type = "topic"
        op.page_name = "the-shire"
        op.content = {"overview": "A hobbit village.", "details": ""}
        op.cross_references = []

        page_path = write_page(op, tmp_path, "> Source: [test]")
        expected = tmp_path / "topics" / "the-shire.md"
        assert page_path == expected
        assert expected.exists()
