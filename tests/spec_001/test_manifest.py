"""Step 1 — Manifest schema validation.

Asserts:
- .claude-plugin/plugin.json exists at the repo root
- Parses as valid JSON
- Contains required fields: name, version, description
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def test_plugin_json_exists() -> None:
    manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert manifest_path.exists(), f"Expected {manifest_path} to exist"


def test_plugin_json_parses_as_json() -> None:
    manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    content = manifest_path.read_text()
    data = json.loads(content)
    assert isinstance(data, dict), "plugin.json must be a JSON object"


def test_plugin_json_has_required_fields() -> None:
    manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest_path.read_text())
    for field in ("name", "version", "description"):
        assert field in data, f"plugin.json missing required field: {field!r}"
    assert data["name"], "name must be non-empty"
    assert data["version"], "version must be non-empty"
    assert data["description"], "description must be non-empty"
