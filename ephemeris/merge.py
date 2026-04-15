"""merge.py — Pure merge and conflict-block functions for ephemeris SPEC-004.

These are pure functions with no filesystem or model dependencies.

Public API:
    render_conflict_block(pair: ConflictPair) -> str
    inject_conflict_blocks(page_content: str, conflicts: list[ConflictPair]) -> str
    apply_merge_additions(page_content: str, additions: list[str]) -> str
    resolve_conflict_block(page_content: str, affirmed_claim: str) -> str
    has_conflict_block(page_content: str) -> bool
"""

from __future__ import annotations

import re

_CONFLICT_MARKER = "> ⚠️ Conflict:"


def render_conflict_block(pair: "ConflictPair") -> str:  # type: ignore[name-defined]  # noqa: F821
    """Render a conflict block for a ConflictPair.

    The block format is exactly as specified by AC-3.2:
        > ⚠️ Conflict: [Session <new-session-id>] asserts "<new claim>"
        > which contradicts the prior claim above [from Session <prior-session-id>].

    Args:
        pair: The ConflictPair to render.

    Returns:
        The conflict block string (no trailing newline beyond one \\n).
    """
    return (
        f'{_CONFLICT_MARKER} [Session {pair.new_session_id}] asserts '
        f'"{pair.new_claim}" which contradicts the prior claim above '
        f'[from Session {pair.existing_session_id}].'
    )


def inject_conflict_blocks(
    page_content: str, conflicts: list["ConflictPair"]  # type: ignore[name-defined]  # noqa: F821
) -> str:
    """Inject conflict blocks into ``page_content`` immediately following
    the contradicted claim.

    For each ConflictPair, locates ``pair.existing_claim`` in the page and
    inserts the rendered conflict block on the next line. If the existing
    claim is not found verbatim, appends the conflict block at the end of
    the page instead (graceful degradation).

    Args:
        page_content: Current page text.
        conflicts: List of ConflictPair objects to inject.

    Returns:
        Modified page content with conflict blocks injected.
    """
    result = page_content
    for pair in conflicts:
        block = render_conflict_block(pair)
        # Don't inject if an identical block already exists
        if block in result:
            continue
        if pair.existing_claim and pair.existing_claim in result:
            # Find the end of the line containing the existing claim
            idx = result.find(pair.existing_claim)
            line_end = result.find("\n", idx)
            if line_end == -1:
                # Claim is on the last line — append at end
                result = result.rstrip("\n") + f"\n{block}\n"
            else:
                result = result[:line_end + 1] + block + "\n" + result[line_end + 1:]
        else:
            # Claim not found verbatim — append at end
            result = result.rstrip("\n") + f"\n\n{block}\n"
    return result


def apply_merge_additions(page_content: str, additions: list[str]) -> str:
    """Append net-new additions to ``page_content``.

    Additions are appended before the ``## Sessions`` section (if present)
    or at the end of the page. Each addition is appended as a paragraph.

    Args:
        page_content: Current page text.
        additions: List of net-new content strings to append.

    Returns:
        Modified page content with additions appended.
    """
    if not additions:
        return page_content

    new_paras = "\n".join(additions)
    sessions_marker = "## Sessions"

    if sessions_marker in page_content:
        idx = page_content.find(sessions_marker)
        return (
            page_content[:idx].rstrip("\n")
            + f"\n\n{new_paras}\n\n"
            + page_content[idx:]
        )
    else:
        return page_content.rstrip("\n") + f"\n\n{new_paras}\n"


def has_conflict_block(page_content: str) -> bool:
    """Return True if the page contains at least one conflict block marker."""
    return _CONFLICT_MARKER in page_content


def resolve_conflict_block(page_content: str, affirmed_claim: str) -> str:
    """Remove an existing conflict block from ``page_content`` when the
    contradiction has been resolved.

    Finds the first conflict block line (starting with ``> ⚠️ Conflict:``)
    and removes it. The affirmed claim is assumed to already be present
    (or will be added by the caller).

    Args:
        page_content: Current page text, which may contain a conflict block.
        affirmed_claim: The claim that was affirmed (for future reference;
                        not added here — caller manages content).

    Returns:
        Page content with the first conflict block line removed.
    """
    lines = page_content.splitlines(keepends=True)
    result_lines = []
    skip_next_blank = False
    for line in lines:
        if line.startswith(_CONFLICT_MARKER):
            skip_next_blank = True
            continue
        if skip_next_blank and line.strip() == "":
            skip_next_blank = False
            continue
        skip_next_blank = False
        result_lines.append(line)
    return "".join(result_lines)
