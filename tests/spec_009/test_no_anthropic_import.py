"""test_no_anthropic_import.py — SPEC-009 AC-1, AC-20.

AST-walks every .py file under ephemeris/ and hooks/ and asserts that
`import anthropic` and `from anthropic` never appear. Also performs a
regex scan for the literal string "anthropic" to catch lazy imports via
importlib.import_module.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCAN_DIRS = [REPO_ROOT / "ephemeris", REPO_ROOT / "hooks"]


def _collect_py_files() -> list[Path]:
    files = []
    for d in SCAN_DIRS:
        files.extend(d.rglob("*.py"))
    return files


def _ast_has_anthropic_import(source: str) -> bool:
    """Return True if the source AST contains any import of anthropic."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "anthropic" or alias.name.startswith("anthropic."):
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "anthropic" or node.module.startswith("anthropic.")
            ):
                return True
    return False


def _regex_has_anthropic_string(source: str) -> bool:
    """Return True if the literal string 'anthropic' appears anywhere."""
    return bool(re.search(r'"anthropic"', source)) or bool(re.search(r"'anthropic'", source))


def test_no_ast_anthropic_import() -> None:
    """No .py file under ephemeris/ or hooks/ imports anthropic."""
    violations: list[str] = []
    for path in _collect_py_files():
        source = path.read_text(encoding="utf-8")
        if _ast_has_anthropic_import(source):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert violations == [], (
        f"Files with `import anthropic` or `from anthropic` imports:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_no_lazy_anthropic_string() -> None:
    """No .py file under ephemeris/ or hooks/ contains the literal string 'anthropic'."""
    violations: list[str] = []
    for path in _collect_py_files():
        source = path.read_text(encoding="utf-8")
        if _regex_has_anthropic_string(source):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert violations == [], (
        f"Files with literal string 'anthropic':\n"
        + "\n".join(f"  {v}" for v in violations)
    )
