"""test_ingest_skill_error_handling.py — SPEC-010 static guard: error handling & summary.

Asserts the commands/ingest.md body contains:
- Retry semantics: the phrase indicating a failed session's JSONL stays in pending/.
- Summary format: lines mentioning 'pages created', 'pages updated', 'contradictions flagged'.
- Empty-queue message: 'No pending sessions to ingest.'
- Unknown session-id message: 'No staged session matches'.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
INGEST_MD = REPO_ROOT / "commands" / "ingest.md"


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
    body = "\n".join(lines[end + 1:])
    return {}, body


def _body() -> str:
    text = INGEST_MD.read_text(encoding="utf-8")
    _, body = _parse_frontmatter(text)
    return body


class TestIngestSkillErrorHandling:
    def test_retry_semantics_stays_in_staging(self) -> None:
        """Body must describe that a failed session's JSONL stays in the per-hook-type
        staging dir (outside processed/) so the next run retries it."""
        body = _body()
        idx_stays = body.find("stays in")
        assert idx_stays != -1, (
            "commands/ingest.md body does not contain 'stays in' — "
            "retry semantics phrase missing"
        )
        # The sentence that follows "stays in" must tie retry to the hook-type
        # staging dir concept. Accept either explicit hook names or the
        # staging_root template variable used in the body.
        window_start = max(0, idx_stays - 200)
        window_end = min(len(body), idx_stays + 400)
        window = body[window_start:window_end]
        anchors = ("<hook-type>", "session-end", "pre-compact", "staging_root")
        assert any(anchor in window for anchor in anchors), (
            "commands/ingest.md: 'stays in' found but no hook-type/staging anchor "
            "within 400 chars — retry semantics phrase incomplete"
        )

    def test_summary_format_pages_created(self) -> None:
        """Body must contain a summary line with 'pages created'."""
        assert "pages created" in _body(), (
            "commands/ingest.md body does not contain 'pages created' in summary format"
        )

    def test_summary_format_pages_updated(self) -> None:
        """Body must contain a summary line with 'pages updated'."""
        assert "pages updated" in _body(), (
            "commands/ingest.md body does not contain 'pages updated' in summary format"
        )

    def test_summary_format_contradictions_flagged(self) -> None:
        """Body must contain a summary line with 'contradictions flagged'."""
        assert "contradictions flagged" in _body(), (
            "commands/ingest.md body does not contain 'contradictions flagged' in summary format"
        )

    def test_empty_queue_message(self) -> None:
        """Body must contain the exact empty-queue stop message."""
        assert "No pending sessions to ingest." in _body(), (
            "commands/ingest.md body does not contain 'No pending sessions to ingest.' message"
        )

    def test_unknown_session_id_message(self) -> None:
        """Body must contain the unknown session-id filter stop message."""
        assert "No staged session matches" in _body(), (
            "commands/ingest.md body does not contain 'No staged session matches' message"
        )
