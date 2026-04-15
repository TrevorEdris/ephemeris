"""test_pyproject_no_anthropic.py — SPEC-009 AC-8, AC-20.

Parses pyproject.toml and asserts that `anthropic` is not listed in
[project.dependencies].
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _parse_dependencies(text: str) -> list[str]:
    """Extract entries from [project] dependencies list."""
    deps: list[str] = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            # Each dep line looks like: `    "anthropic>=0.20.0",`
            dep = stripped.strip('",').strip()
            if dep:
                deps.append(dep)
    return deps


def test_anthropic_not_in_dependencies() -> None:
    """pyproject.toml must not list anthropic as a runtime dependency."""
    text = PYPROJECT.read_text(encoding="utf-8")
    deps = _parse_dependencies(text)
    anthropic_deps = [d for d in deps if d.lower().startswith("anthropic")]
    assert anthropic_deps == [], (
        f"pyproject.toml still lists anthropic in dependencies: {anthropic_deps}"
    )


def test_anthropic_string_absent_from_dependencies_section() -> None:
    """The literal word 'anthropic' must not appear in the dependencies array."""
    text = PYPROJECT.read_text(encoding="utf-8")
    # Parse out just the dependencies block
    lines = text.splitlines()
    in_deps = False
    dep_lines: list[str] = []
    for line in lines:
        if line.strip() == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if line.strip() == "]":
                break
            dep_lines.append(line)
    dep_block = "\n".join(dep_lines)
    assert "anthropic" not in dep_block.lower(), (
        f"anthropic found in dependencies block:\n{dep_block}"
    )
