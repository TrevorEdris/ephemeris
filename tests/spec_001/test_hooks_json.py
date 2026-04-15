"""Step 2 — hooks/hooks.json schema validation.

Asserts:
- hooks/hooks.json exists
- Parses as valid JSON
- Declares a SessionEnd hook and a PreCompact hook
- Each hook command points to an existing .py file under hooks/
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_hooks() -> dict:
    hooks_path = REPO_ROOT / "hooks" / "hooks.json"
    assert hooks_path.exists(), f"Expected {hooks_path} to exist"
    data = json.loads(hooks_path.read_text())
    assert isinstance(data, dict), "hooks.json must be a JSON object"
    return data


def test_hooks_json_exists() -> None:
    hooks_path = REPO_ROOT / "hooks" / "hooks.json"
    assert hooks_path.exists(), f"Expected {hooks_path} to exist"


def test_hooks_json_parses_as_json() -> None:
    _load_hooks()


def test_hooks_json_declares_session_end_hook() -> None:
    data = _load_hooks()
    hooks = data.get("hooks", {})
    assert "SessionEnd" in hooks, "hooks.json must declare a SessionEnd hook"
    session_end_entries = hooks["SessionEnd"]
    assert isinstance(session_end_entries, list) and len(session_end_entries) > 0, (
        "SessionEnd must have at least one hook entry"
    )


def test_hooks_json_declares_pre_compact_hook() -> None:
    data = _load_hooks()
    hooks = data.get("hooks", {})
    assert "PreCompact" in hooks, "hooks.json must declare a PreCompact hook"
    pre_compact_entries = hooks["PreCompact"]
    assert isinstance(pre_compact_entries, list) and len(pre_compact_entries) > 0, (
        "PreCompact must have at least one hook entry"
    )


def _extract_py_path_from_command(command: str) -> Path:
    """Parse 'python3 ${CLAUDE_PLUGIN_ROOT}/hooks/foo.py' → repo-relative path."""
    # Strip the interpreter prefix and resolve the CLAUDE_PLUGIN_ROOT placeholder
    # to the repo root for testing purposes.
    parts = command.split("${CLAUDE_PLUGIN_ROOT}/")
    assert len(parts) == 2, f"Unexpected command format: {command!r}"
    relative = parts[1]
    return REPO_ROOT / relative


def _get_hook_py_paths(hook_entries: list) -> list[Path]:
    paths: list[Path] = []
    for entry in hook_entries:
        inner_hooks = entry.get("hooks", [])
        for hook in inner_hooks:
            cmd = hook.get("command", "")
            if cmd:
                paths.append(_extract_py_path_from_command(cmd))
    return paths


def test_session_end_hook_py_file_exists() -> None:
    data = _load_hooks()
    entries = data["hooks"]["SessionEnd"]
    py_paths = _get_hook_py_paths(entries)
    assert py_paths, "SessionEnd hook must have at least one command"
    for path in py_paths:
        assert path.exists(), f"SessionEnd hook script not found: {path}"
        assert path.suffix == ".py", f"Expected a .py file, got: {path}"


def test_pre_compact_hook_py_file_exists() -> None:
    data = _load_hooks()
    entries = data["hooks"]["PreCompact"]
    py_paths = _get_hook_py_paths(entries)
    assert py_paths, "PreCompact hook must have at least one command"
    for path in py_paths:
        assert path.exists(), f"PreCompact hook script not found: {path}"
        assert path.suffix == ".py", f"Expected a .py file, got: {path}"
