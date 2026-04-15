"""test_atomic_wiki_writes.py — SPEC-003 atomic write tests for wiki.py.

Verifies that wiki page writes are atomic (temp-then-rename) so no partial
files appear at the target path on failure or concurrent access.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from ephemeris.wiki import _atomic_write_text


class TestNoTmpFileRemainsAfterSuccess:
    """No .tmp files left after a successful write."""

    def test_no_tmp_file_remains_after_successful_write(self, tmp_path: Path) -> None:
        target = tmp_path / "page.md"
        _atomic_write_text(target, "hello world")
        assert target.read_text() == "hello world"
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Unexpected .tmp files: {tmp_files}"


class TestNoPartialFileOnFailure:
    """Target file is unchanged (or absent) when write fails mid-way."""

    def test_no_partial_file_when_write_fails_midway(self, tmp_path: Path) -> None:
        target = tmp_path / "page.md"
        original_content = "original content"
        target.write_text(original_content)

        def bad_fdopen(fd: int, *args, **kwargs):
            os.close(fd)  # close the fd to avoid leak
            raise IOError("simulated mid-write failure")

        with patch("ephemeris.wiki.os.fdopen", side_effect=bad_fdopen):
            with pytest.raises(IOError, match="simulated mid-write failure"):
                _atomic_write_text(target, "new content")

        # Target file must be unchanged
        assert target.read_text() == original_content
        # No .tmp detritus
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Unexpected .tmp files: {tmp_files}"


class TestConcurrentAtomicWrites:
    """Concurrent writes to the same path never produce a corrupt mix."""

    def test_concurrent_atomic_writes_dont_corrupt(self, tmp_path: Path) -> None:
        target = tmp_path / "page.md"
        content_a = "A" * 10_000
        content_b = "B" * 10_000

        errors: list[Exception] = []

        def write_a() -> None:
            try:
                _atomic_write_text(target, content_a)
            except Exception as exc:
                errors.append(exc)

        def write_b() -> None:
            try:
                _atomic_write_text(target, content_b)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=write_a)
        t2 = threading.Thread(target=write_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Thread errors: {errors}"
        final = target.read_text()
        assert final in (content_a, content_b), (
            f"File content is neither A nor B (got {len(final)} chars starting with {final[:20]!r})"
        )
