"""tests/spec_007/test_hook_scope_integration.py — SPEC-007 hook scope integration.

Covers:
    AC-1: no config file → capture runs normally
    AC-2: cwd matches include → capture runs
    AC-3/AC-6: cwd matches exclude → capture skipped, no staging file
    AC-4: hot-reload — config change between invocations takes effect
    AC-5: invalid JSON config → falls back to all-capture, warning logged
    AC-7: cwd not in include → capture skipped

Tests both post_session.py and pre_compact.py hooks.

Hook entry points are invoked as Python functions (import and call main())
with stdin patched and env vars set via monkeypatch.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(
    tmp_path: Path,
    cwd: str = "/work/project",
    session_id: str = "test-session-001",
) -> dict[str, Any]:
    """Create a minimal valid hook payload with a non-empty transcript file."""
    transcript_file = tmp_path / f"{session_id}.jsonl"
    transcript_file.write_text(
        '{"role": "user", "content": "hello"}\n', encoding="utf-8"
    )
    return {
        "session_id": session_id,
        "transcript_path": str(transcript_file),
        "cwd": cwd,
    }


def _run_hook(hook_module_path: str, payload: dict[str, Any], env_overrides: dict[str, str], monkeypatch, capsys=None) -> str:
    """Run a hook's main() with a patched stdin and env. Returns captured stdout."""
    import importlib

    payload_str = json.dumps(payload)

    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)

    # Patch stdin with the payload
    with patch("sys.stdin", io.StringIO(payload_str)):
        # Re-import to get fresh module state
        if hook_module_path in sys.modules:
            del sys.modules[hook_module_path]
        # Also clear _lib modules to reset
        for key in list(sys.modules.keys()):
            if key.startswith("_lib"):
                del sys.modules[key]

        # Capture print output
        captured_output = io.StringIO()
        with patch("sys.stdout", captured_output):
            # Import the hook module from file path, not module name
            hooks_dir = Path(__file__).parent.parent.parent / "hooks"
            sys.path.insert(0, str(hooks_dir))
            sys.path.insert(0, str(hooks_dir.parent))
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    hook_module_path,
                    hooks_dir / f"{hook_module_path}.py",
                )
                mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                # Provide a fresh stdin for the module
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                mod.main()
            finally:
                if str(hooks_dir) in sys.path:
                    sys.path.remove(str(hooks_dir))

        return captured_output.getvalue()


# ---------------------------------------------------------------------------
# AC-1 — no config file → capture runs normally
# ---------------------------------------------------------------------------

class TestPostSessionNoConfig:
    """When no scope config exists, capture() is called normally."""

    def test_post_session_no_config_runs_capture_normally(
        self, tmp_path, monkeypatch
    ):
        """No scope file → capture is called, staging file is created."""
        from ephemeris import capture as capture_module

        call_count = {"n": 0}
        original_capture = capture_module.capture

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1
            return original_capture(*args, **kwargs)

        payload = _make_payload(tmp_path)
        staging_root = tmp_path / "staging"

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(tmp_path / "no_such_scope.json"))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            _run_hook("post_session", payload, {}, monkeypatch)

        assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# AC-3/AC-6 — exclude match → skip capture
# ---------------------------------------------------------------------------

class TestPostSessionExcludeSkip:
    """When cwd matches exclude rule, capture() is not called."""

    def test_post_session_skip_when_cwd_matches_exclude(
        self, tmp_path, monkeypatch
    ):
        """Exclude rule matching payload's cwd → capture not called, no staging file."""
        scope_file = tmp_path / "scope.json"
        scope_file.write_text(
            json.dumps({"include": [], "exclude": ["/work/**"]}), encoding="utf-8"
        )

        payload = _make_payload(tmp_path, cwd="/work/project")
        staging_root = tmp_path / "staging"

        call_count = {"n": 0}

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(scope_file))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            output = _run_hook("post_session", payload, {}, monkeypatch)

        assert call_count["n"] == 0
        # No staging files should exist
        assert not staging_root.exists() or not any(staging_root.rglob("*.jsonl"))

    def test_post_session_skip_returns_skipped_status(
        self, tmp_path, monkeypatch
    ):
        """Hook returns status=skipped when out of scope."""
        scope_file = tmp_path / "scope.json"
        scope_file.write_text(
            json.dumps({"exclude": ["/work/**"]}), encoding="utf-8"
        )

        payload = _make_payload(tmp_path, cwd="/work/project")
        staging_root = tmp_path / "staging"

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(scope_file))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        output = _run_hook("post_session", payload, {}, monkeypatch)
        result = json.loads(output)
        assert result.get("status") == "skipped"
        assert result.get("reason") == "out_of_scope"


# ---------------------------------------------------------------------------
# AC-7 — cwd not in include → skip capture
# ---------------------------------------------------------------------------

class TestPostSessionIncludeNonMatch:
    """When include rules exist but cwd doesn't match, capture is skipped."""

    def test_post_session_skip_when_cwd_not_in_include(
        self, tmp_path, monkeypatch
    ):
        """Include rule for path A, payload cwd is B → capture not called."""
        scope_file = tmp_path / "scope.json"
        scope_file.write_text(
            json.dumps({"include": ["/allowed/**"], "exclude": []}), encoding="utf-8"
        )

        payload = _make_payload(tmp_path, cwd="/notallowed/project")
        staging_root = tmp_path / "staging"

        call_count = {"n": 0}

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(scope_file))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            _run_hook("post_session", payload, {}, monkeypatch)

        assert call_count["n"] == 0


# ---------------------------------------------------------------------------
# AC-2 — include match → capture runs
# ---------------------------------------------------------------------------

class TestPostSessionIncludeMatch:
    """When cwd matches an include rule, capture runs."""

    def test_post_session_ingest_when_cwd_in_include(
        self, tmp_path, monkeypatch
    ):
        """Include rule matches cwd → capture is called."""
        scope_file = tmp_path / "scope.json"
        scope_file.write_text(
            json.dumps({"include": ["/work/**"], "exclude": []}), encoding="utf-8"
        )

        payload = _make_payload(tmp_path, cwd="/work/myproject")
        staging_root = tmp_path / "staging"

        call_count = {"n": 0}
        original_capture = __import__("ephemeris.capture", fromlist=["capture"]).capture

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1
            return original_capture(*args, **kwargs)

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(scope_file))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            _run_hook("post_session", payload, {}, monkeypatch)

        assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# AC-4 — hot-reload between invocations
# ---------------------------------------------------------------------------

class TestPostSessionHotReload:
    """Config changes take effect on next hook invocation without restart."""

    def test_post_session_hot_reload_between_invocations(
        self, tmp_path, monkeypatch
    ):
        """First call with empty config → capture. Write exclude. Second call → skip."""
        scope_file = tmp_path / "scope.json"
        # Start with empty (allow-all) config
        scope_file.write_text(json.dumps({}), encoding="utf-8")

        payload = _make_payload(tmp_path, cwd="/work/project")
        staging_root = tmp_path / "staging"

        call_counts = {"n": 0}
        original_capture = __import__("ephemeris.capture", fromlist=["capture"]).capture

        def spy_capture(*args, **kwargs):
            call_counts["n"] += 1
            return original_capture(*args, **kwargs)

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(scope_file))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        # First invocation — should capture
        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            _run_hook("post_session", payload, {}, monkeypatch)
        assert call_counts["n"] == 1

        # Update config to exclude /work/**
        scope_file.write_text(
            json.dumps({"exclude": ["/work/**"]}), encoding="utf-8"
        )

        # Second invocation — should skip
        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            _run_hook("post_session", payload, {}, monkeypatch)
        assert call_counts["n"] == 1  # unchanged — capture was not called again


# ---------------------------------------------------------------------------
# AC-5 — invalid config → all-capture fallback + warning
# ---------------------------------------------------------------------------

class TestPostSessionInvalidConfigFallback:
    """Invalid JSON config → capture still runs, warning is emitted."""

    def test_post_session_invalid_config_falls_back_to_capture(
        self, tmp_path, monkeypatch, caplog
    ):
        """Invalid JSON in scope config → capture IS called + warning logged."""
        import logging

        bad_scope_file = tmp_path / "scope.json"
        bad_scope_file.write_text("not-valid-json{{{", encoding="utf-8")

        payload = _make_payload(tmp_path, cwd="/work/project")
        staging_root = tmp_path / "staging"

        call_count = {"n": 0}
        original_capture = __import__("ephemeris.capture", fromlist=["capture"]).capture

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1
            return original_capture(*args, **kwargs)

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(bad_scope_file))
        monkeypatch.setenv("EPHEMERIS_INGEST_ON_CAPTURE", "0")

        with caplog.at_level(logging.WARNING, logger="ephemeris.scope"):
            with patch("ephemeris.capture.capture", side_effect=spy_capture):
                _run_hook("post_session", payload, {}, monkeypatch)

        assert call_count["n"] == 1
        assert any(
            "invalid JSON" in rec.message or "invalid json" in rec.message.lower()
            for rec in caplog.records
        ), f"Expected warning, got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# pre_compact.py mirror tests
# ---------------------------------------------------------------------------

class TestPreCompactScopeIntegration:
    """Mirror of post_session tests for pre_compact.py."""

    def test_pre_compact_no_config_runs_capture_normally(
        self, tmp_path, monkeypatch
    ):
        """No scope file → pre_compact capture is called."""
        from ephemeris import capture as capture_module

        call_count = {"n": 0}
        original_capture = capture_module.capture

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1
            return original_capture(*args, **kwargs)

        payload = _make_payload(tmp_path, cwd="/work/project")
        staging_root = tmp_path / "staging"

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(tmp_path / "no_such_scope.json"))

        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            _run_hook("pre_compact", payload, {}, monkeypatch)

        assert call_count["n"] == 1

    def test_pre_compact_skip_when_cwd_matches_exclude(
        self, tmp_path, monkeypatch
    ):
        """Exclude rule matches cwd → pre_compact capture not called."""
        scope_file = tmp_path / "scope.json"
        scope_file.write_text(
            json.dumps({"exclude": ["/work/**"]}), encoding="utf-8"
        )

        payload = _make_payload(tmp_path, cwd="/work/project")
        staging_root = tmp_path / "staging"

        call_count = {"n": 0}

        def spy_capture(*args, **kwargs):
            call_count["n"] += 1

        monkeypatch.setenv("EPHEMERIS_STAGING_ROOT", str(staging_root))
        monkeypatch.setenv("EPHEMERIS_SCOPE_CONFIG", str(scope_file))

        with patch("ephemeris.capture.capture", side_effect=spy_capture):
            output = _run_hook("pre_compact", payload, {}, monkeypatch)

        assert call_count["n"] == 0
        result = json.loads(output)
        assert result.get("status") == "skipped"
        assert result.get("reason") == "out_of_scope"
