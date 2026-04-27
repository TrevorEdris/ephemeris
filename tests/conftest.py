"""tests/conftest.py — collection-time exclusions for v0.2.0 deprecations.

The hook capture pipeline and the v0.1.x slash-command body are deprecated.
The corresponding tests are preserved for git history but excluded from
collection so the suite stays green.
"""

from __future__ import annotations

# Paths are relative to this conftest.py file.
collect_ignore_glob = [
    "spec_002/test_hook_capture_integration.py",
    "spec_007/test_hook_scope_integration.py",
    "spec_009/test_commands_are_stubs.py",
    "spec_010/test_ingest_skill_body.py",
    "spec_010/test_ingest_skill_error_handling.py",
]

# Individual hook-invoking tests inside otherwise-still-relevant files.
collect_ignore = []


def pytest_collection_modifyitems(config, items):
    """Skip individual hook-invoking tests that exercise the deprecated capture."""
    import pytest as _pytest

    deprecated_node_ids = {
        "tests/spec_002/test_capture.py::test_post_session_invokes_capture_and_exits_zero",
        "tests/spec_002/test_capture.py::test_pre_compact_invokes_capture_and_exits_zero",
    }
    skip_marker = _pytest.mark.skip(reason="hook capture deprecated in v0.2.0")
    for item in items:
        nodeid_norm = item.nodeid
        # The CWD-relative prefix may be absent; match by suffix.
        if any(nodeid_norm.endswith(d) for d in deprecated_node_ids):
            item.add_marker(skip_marker)
