"""test_schema_bootstrap.py — SPEC-009 AC-11, AC-13, AC-20.

Five test cases for bootstrap_default_schema():

1. Dest missing → copies source to dest → dest exists and matches source bytes.
2. Dest present and newer than source → no-op (mtime check).
3. Dest present but older than source → overwritten with source bytes.
4. Source missing → function returns cleanly (fail-soft), dest unchanged,
   warning logged.
5. Dest parent directory missing → creates parent + copies.

All tests use tmp_path fixtures; none touch real user state.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest


def test_copies_when_dest_missing(tmp_path: Path) -> None:
    """Case 1: dest missing → copies source to dest."""
    src = tmp_path / "source" / "default.md"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"# Ephemeris Wiki Schema\n\nSome content.\n")

    dst = tmp_path / "dest" / "default-schema.md"
    dst.parent.mkdir(parents=True)
    # dst does NOT exist

    from ephemeris.capture import bootstrap_default_schema

    bootstrap_default_schema(source_path=src, dest_path=dst)

    assert dst.exists(), "bootstrap_default_schema should create dest when missing"
    assert dst.read_bytes() == src.read_bytes(), "dest bytes should match source bytes"


def test_noop_when_dest_newer(tmp_path: Path) -> None:
    """Case 2: dest newer than source → no-op."""
    src = tmp_path / "source" / "default.md"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"# Ephemeris Wiki Schema\n\nOriginal content.\n")

    dst = tmp_path / "dest" / "default-schema.md"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"# Already here - different content\n")

    # Make dest newer than source by bumping its mtime
    src_mtime = src.stat().st_mtime
    os.utime(dst, (src_mtime + 10, src_mtime + 10))

    original_dst_bytes = dst.read_bytes()

    from ephemeris.capture import bootstrap_default_schema

    bootstrap_default_schema(source_path=src, dest_path=dst)

    assert dst.read_bytes() == original_dst_bytes, (
        "bootstrap_default_schema should NOT overwrite a newer dest"
    )


def test_overwrites_when_dest_older(tmp_path: Path) -> None:
    """Case 3: dest older than source → overwritten with source bytes."""
    src = tmp_path / "source" / "default.md"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"# Ephemeris Wiki Schema\n\nNewer source content.\n")

    dst = tmp_path / "dest" / "default-schema.md"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"# Old content\n")

    # Make dest older than source
    src_mtime = src.stat().st_mtime
    os.utime(dst, (src_mtime - 10, src_mtime - 10))

    from ephemeris.capture import bootstrap_default_schema

    bootstrap_default_schema(source_path=src, dest_path=dst)

    assert dst.read_bytes() == src.read_bytes(), (
        "bootstrap_default_schema should overwrite dest when it is older than source"
    )


def test_fail_soft_when_source_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Case 4: source missing → returns cleanly, dest unchanged, warning logged."""
    src = tmp_path / "nonexistent" / "default.md"
    # src does NOT exist

    dst = tmp_path / "dest" / "default-schema.md"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"# Existing content\n")
    original_bytes = dst.read_bytes()

    from ephemeris.capture import bootstrap_default_schema

    import logging
    with caplog.at_level(logging.WARNING):
        # Must not raise
        bootstrap_default_schema(source_path=src, dest_path=dst)

    assert dst.read_bytes() == original_bytes, (
        "bootstrap_default_schema should leave dest unchanged when source is missing"
    )


def test_creates_parent_directory(tmp_path: Path) -> None:
    """Case 5: dest parent directory missing → creates parent + copies."""
    src = tmp_path / "source" / "default.md"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"# Ephemeris Wiki Schema\n\nContent here.\n")

    # Dest parent does NOT exist
    dst = tmp_path / "deep" / "nested" / "path" / "default-schema.md"
    assert not dst.parent.exists(), "test setup: dest parent should not exist"

    from ephemeris.capture import bootstrap_default_schema

    bootstrap_default_schema(source_path=src, dest_path=dst)

    assert dst.exists(), "bootstrap_default_schema should create parent dirs and dest"
    assert dst.read_bytes() == src.read_bytes(), "dest bytes should match source bytes"
