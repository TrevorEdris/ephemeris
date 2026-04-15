"""test_readme_no_api_key.py — SPEC-009 AC-9, AC-20.

Asserts that ANTHROPIC_API_KEY does not appear in README.md.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
README = REPO_ROOT / "README.md"


def test_readme_no_anthropic_api_key() -> None:
    """README.md must not contain ANTHROPIC_API_KEY."""
    text = README.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in text, (
        "README.md still contains ANTHROPIC_API_KEY — strip it per AC-9"
    )
