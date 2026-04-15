"""test_schema_bootstrap.py — Slice 1: Schema Bootstrap tests.

Tests AC-1.1 through AC-1.4 of SPEC-003.
"""

from __future__ import annotations

from pathlib import Path


def test_bootstrap_writes_schema_on_first_run(tmp_path: Path) -> None:
    """AC-1.1: Given no wiki, bootstrap writes SCHEMA.md to wiki root."""
    from ephemeris.schema import bootstrap_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_path = wiki_root / "SCHEMA.md"

    assert not schema_path.exists()
    bootstrap_schema(wiki_root)
    assert schema_path.exists()
    assert schema_path.stat().st_size > 0


def test_bootstrap_works_offline_no_network(tmp_path: Path, monkeypatch: object) -> None:
    """AC-1.4: Schema bootstrap requires no network — works offline."""
    import socket

    from ephemeris.schema import bootstrap_schema

    # Patch socket.socket to block any network attempt
    def refuse_connect(*args: object, **kwargs: object) -> None:  # type: ignore[override]
        raise OSError("Network access blocked in test")

    monkeypatch.setattr(socket, "socket", refuse_connect)

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    # Must not raise even though network is blocked
    bootstrap_schema(wiki_root)
    assert (wiki_root / "SCHEMA.md").exists()


def test_bootstrap_schema_content_has_all_page_types(tmp_path: Path) -> None:
    """AC-1.3: Bootstrapped schema contains all three page type definitions."""
    from ephemeris.schema import bootstrap_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    bootstrap_schema(wiki_root)

    content = (wiki_root / "SCHEMA.md").read_text(encoding="utf-8")
    assert "wiki/topics/" in content, "Schema must define Topic page directory"
    assert "wiki/entities/" in content, "Schema must define Entity page directory"
    assert "DECISIONS.md" in content, "Schema must define Decision Log file"
    # Naming conventions present
    assert "kebab-case" in content, "Schema must specify kebab-case for topics"
    assert "PascalCase" in content, "Schema must specify PascalCase for entities"


def test_bootstrap_skips_existing_schema(tmp_path: Path) -> None:
    """AC-1.2: Given existing SCHEMA.md, bootstrap does not overwrite it."""
    from ephemeris.schema import bootstrap_schema

    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    schema_path = wiki_root / "SCHEMA.md"

    sentinel = "SENTINEL_DO_NOT_OVERWRITE"
    schema_path.write_text(sentinel, encoding="utf-8")

    bootstrap_schema(wiki_root)

    assert schema_path.read_text(encoding="utf-8") == sentinel
