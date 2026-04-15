"""wiki.py — Wiki page write and merge helpers for ephemeris.

Handles creation and append-only updates for the three wiki page types:
- Topic pages:   wiki/topics/<kebab-case>.md
- Entity pages:  wiki/entities/<PascalCase>.md
- Decision log:  wiki/DECISIONS.md (single shared file, newest-first)

Full merge / contradiction detection lands in SPEC-004. This module
implements append-only merging: existing content is preserved and new
session content is appended.

Public API:
    write_page(op, wiki_root, citation) -> Path
    append_to_decisions(op, wiki_root, citation) -> Path
    add_cross_references(wiki_root, page_path, cross_references) -> None
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ephemeris.prompts import PageOperation


_PAGE_NAME_FORBIDDEN = ("..", "/", "\\", ":", "\x00")


def _sanitize_page_name(name: str) -> str:
    """Reject any page_name that could escape the wiki root or hit reserved chars.

    Only bare filenames are allowed. Model-generated names that include path
    separators, parent refs, or drive letters are rejected outright — we do not
    try to 'fix' them, because any fix opens the door to further bypass.

    Raises:
        WikiWriteError: If the name is empty, contains forbidden tokens, or is
                        not a bare filename component.
    """
    from ephemeris.exceptions import WikiWriteError

    if not name or not name.strip():
        raise WikiWriteError("page_name is empty")
    stripped = name.strip()
    for token in _PAGE_NAME_FORBIDDEN:
        if token in stripped:
            raise WikiWriteError(
                f"page_name contains forbidden token {token!r}: {stripped!r}"
            )
    # Also reject if pathlib sees it as anything other than a single component.
    if Path(stripped).name != stripped:
        raise WikiWriteError(f"page_name must be a bare filename: {stripped!r}")
    return stripped


def _assert_contained(page_path: Path, wiki_root: Path) -> None:
    """Raise WikiWriteError if page_path escapes wiki_root (belt-and-suspenders)."""
    from ephemeris.exceptions import WikiWriteError

    resolved = page_path.resolve()
    wiki_root_resolved = wiki_root.resolve()
    if not resolved.is_relative_to(wiki_root_resolved):
        raise WikiWriteError(f"page_path escapes wiki_root: {resolved}")


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace ``path`` with ``content``.

    Writes to a temp file in the same directory (same filesystem, so
    os.replace is atomic on POSIX), then renames into place. Partial writes
    never appear at ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def write_page(
    op: "PageOperation",
    wiki_root: Path,
    citation: str,
) -> Path:
    """Write or update a wiki page based on a PageOperation.

    - For ``decision`` page_type, delegates to ``append_to_decisions``.
    - For ``topic`` and ``entity``, creates a new page or appends a new
      session section to an existing page.

    Args:
        op: Parsed PageOperation from the model response.
        wiki_root: Root directory of the wiki.
        citation: Citation string, e.g. ``"> Source: [2026-04-15 session-abc]"``.

    Returns:
        Path to the written or updated wiki page file.

    Raises:
        WikiWriteError: If the file cannot be written.
    """
    from ephemeris.exceptions import WikiWriteError

    try:
        if op.page_type == "decision":
            return append_to_decisions(op, wiki_root, citation)
        elif op.page_type == "topic":
            return _write_topic(op, wiki_root, citation)
        elif op.page_type == "entity":
            return _write_entity(op, wiki_root, citation)
        else:
            raise WikiWriteError(f"Unknown page_type: {op.page_type!r}")
    except WikiWriteError:
        raise
    except OSError as exc:
        raise WikiWriteError(f"Failed to write page {op.page_name!r}: {exc}") from exc


def _write_topic(
    op: "PageOperation",
    wiki_root: Path,
    citation: str,
) -> Path:
    """Create or update a topic page at wiki/topics/<kebab-case>.md."""
    safe_name = _sanitize_page_name(op.page_name)
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    page_path = topics_dir / f"{safe_name}.md"
    _assert_contained(page_path, wiki_root)

    overview = op.content.get("overview", "")
    details = op.content.get("details", "")

    if not page_path.exists():
        # Create new page
        content = f"# {_title(safe_name)}\n\n"
        if overview:
            content += f"## Overview\n{overview}\n\n"
        if details:
            content += f"## Details\n{details}\n\n"
        content += f"## Sessions\n{citation}\n"
        _atomic_write_text(page_path, content)
    else:
        # Append session section — preserve existing content
        existing = page_path.read_text(encoding="utf-8")
        new_section = ""
        if details:
            new_section += f"\n{details}\n"
        # Append to ## Sessions section
        if "## Sessions" in existing:
            existing = existing.rstrip() + f"\n{citation}\n"
        else:
            existing = existing.rstrip() + f"\n\n## Sessions\n{citation}\n"
        if new_section:
            # Insert before ## Sessions
            sessions_idx = existing.find("## Sessions")
            existing = (
                existing[:sessions_idx]
                + new_section
                + existing[sessions_idx:]
            )
        _atomic_write_text(page_path, existing)

    return page_path


def _write_entity(
    op: "PageOperation",
    wiki_root: Path,
    citation: str,
) -> Path:
    """Create or update an entity page at wiki/entities/<PascalCase>.md."""
    safe_name = _sanitize_page_name(op.page_name)
    entities_dir = wiki_root / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    page_path = entities_dir / f"{safe_name}.md"
    _assert_contained(page_path, wiki_root)

    role = op.content.get("role", "")
    relationships: list[dict[str, str]] = op.content.get("relationships", [])

    if not page_path.exists():
        # Create new page
        content = f"# {safe_name}\n\n"
        if role:
            content += f"## Role\n{role}\n\n"
        if relationships:
            content += "## Relationships\n"
            for rel in relationships:
                entity_name = rel.get("entity", "")
                description = rel.get("description", "")
                if entity_name:
                    content += f"- [{entity_name}]({entity_name}.md) — {description}\n"
            content += "\n"
        content += f"## Sessions\n{citation}\n"
        _atomic_write_text(page_path, content)
    else:
        # Append session info — preserve existing content
        existing = page_path.read_text(encoding="utf-8")
        # Add new relationships if any (deduplicated by entity name)
        if relationships:
            for rel in relationships:
                entity_name = rel.get("entity", "")
                if entity_name and f"[{entity_name}]" not in existing:
                    description = rel.get("description", "")
                    rel_line = f"- [{entity_name}]({entity_name}.md) — {description}\n"
                    if "## Relationships" in existing:
                        # Insert after ## Relationships heading
                        rel_idx = existing.find("## Relationships") + len("## Relationships\n")
                        existing = existing[:rel_idx] + rel_line + existing[rel_idx:]
                    else:
                        # Add relationships section before ## Sessions
                        sessions_idx = existing.find("## Sessions")
                        if sessions_idx == -1:
                            existing = existing.rstrip() + f"\n\n## Relationships\n{rel_line}"
                        else:
                            existing = (
                                existing[:sessions_idx]
                                + f"## Relationships\n{rel_line}\n"
                                + existing[sessions_idx:]
                            )
        # Append citation
        if "## Sessions" in existing:
            existing = existing.rstrip() + f"\n{citation}\n"
        else:
            existing = existing.rstrip() + f"\n\n## Sessions\n{citation}\n"
        _atomic_write_text(page_path, existing)

    return page_path


def append_to_decisions(
    op: "PageOperation",
    wiki_root: Path,
    citation: str,
) -> Path:
    """Prepend a new entry to wiki/DECISIONS.md (newest-first).

    Args:
        op: PageOperation with page_type='decision'.
        wiki_root: Root directory of the wiki.
        citation: Citation string.

    Returns:
        Path to DECISIONS.md.
    """
    safe_name = _sanitize_page_name(op.page_name)
    decisions_path = wiki_root / "DECISIONS.md"

    decision_text = op.content.get("decision", "")
    rationale = op.content.get("rationale", "")
    date = op.content.get("date", "")

    entry = f"## [{date}] {safe_name}\n\n"
    if decision_text:
        entry += f"**Decision:** {decision_text}\n\n"
    if rationale:
        entry += f"**Rationale:** {rationale}\n\n"
    entry += f"**Session:** {citation}\n\n---\n\n"

    if decisions_path.exists():
        existing = decisions_path.read_text(encoding="utf-8")
        # Prepend new entry (newest-first)
        new_content = entry + existing
    else:
        new_content = "# Decision Log\n\n" + entry

    _atomic_write_text(decisions_path, new_content)
    return decisions_path


def add_cross_references(
    wiki_root: Path,
    source_page: Path,
    cross_references: list[str],
    page_type_map: dict[str, str],
) -> None:
    """Add cross-reference links to a source page and back-link the targets.

    Links are only added if not already present. This implements basic
    bidirectional linking; full cross-reference resolution is in SPEC-004.

    Args:
        wiki_root: Root directory of the wiki.
        source_page: Path to the page that contains cross_references.
        cross_references: List of page names this page references.
        page_type_map: Mapping of page_name -> page_type for all operations
                       in the current ingestion run.
    """
    if not cross_references:
        return

    try:
        source_content = source_page.read_text(encoding="utf-8")
    except OSError:
        return

    source_dir = source_page.parent
    modified = False

    for ref_name in cross_references:
        ref_type = page_type_map.get(ref_name)
        if ref_type == "topic":
            ref_path = wiki_root / "topics" / f"{ref_name}.md"
            rel_link = f"[{ref_name}](../topics/{ref_name}.md)"
        elif ref_type == "entity":
            ref_path = wiki_root / "entities" / f"{ref_name}.md"
            rel_link = f"[{ref_name}](../entities/{ref_name}.md)"
        else:
            # Unknown type — try to find the file
            topic_path = wiki_root / "topics" / f"{ref_name}.md"
            entity_path = wiki_root / "entities" / f"{ref_name}.md"
            if topic_path.exists():
                ref_path = topic_path
                rel_link = f"[{ref_name}](../topics/{ref_name}.md)"
            elif entity_path.exists():
                ref_path = entity_path
                rel_link = f"[{ref_name}](../entities/{ref_name}.md)"
            else:
                continue

        # Add link to source page if not already there
        if rel_link not in source_content:
            source_content = source_content.rstrip() + f"\n\n## See Also\n- {rel_link}\n"
            modified = True

        # Back-link: add a reference from ref_page to source_page
        _add_back_link(ref_path, source_page, wiki_root)

    if modified:
        try:
            _atomic_write_text(source_page, source_content)
        except OSError:
            pass


def _add_back_link(ref_path: Path, source_page: Path, wiki_root: Path) -> None:
    """Add a back-link from ref_path to source_page if not already present."""
    if not ref_path.exists():
        return
    try:
        ref_content = ref_path.read_text(encoding="utf-8")
    except OSError:
        return

    # Compute relative link from ref to source
    source_name = source_page.stem
    source_dir_name = source_page.parent.name  # 'topics' or 'entities'
    back_link = f"[{source_name}](../{source_dir_name}/{source_page.name})"

    if back_link not in ref_content:
        ref_content = ref_content.rstrip() + f"\n\n## See Also\n- {back_link}\n"
        try:
            _atomic_write_text(ref_path, ref_content)
        except OSError:
            pass


def _load_page(op: "PageOperation", wiki_root: Path) -> str | None:
    """Return the existing page content for ``op``, or None if not found.

    Only topic and entity pages are checked; decisions always append.

    Args:
        op: PageOperation to look up.
        wiki_root: Root directory of the wiki.

    Returns:
        Page text as a string, or None if the page does not yet exist.
    """
    if op.page_type == "topic":
        safe_name = _sanitize_page_name(op.page_name)
        page_path = wiki_root / "topics" / f"{safe_name}.md"
    elif op.page_type == "entity":
        safe_name = _sanitize_page_name(op.page_name)
        page_path = wiki_root / "entities" / f"{safe_name}.md"
    else:
        return None

    if not page_path.exists():
        return None
    try:
        return page_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _title(kebab_name: str) -> str:
    """Convert a kebab-case page name to a human-readable title."""
    return kebab_name.replace("-", " ").title()
