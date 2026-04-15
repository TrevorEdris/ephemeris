# SPEC-007: Capture Scope Configuration

**Feature ID:** P2-A
**Size:** SMALL
**Risk:** LOW
**Status:** DRAFT

## Problem Statement

Ephemeris currently ingests all session content without discrimination. Users working across multiple projects or sensitive topic areas need a way to limit which content enters the wiki. Without a configurable scope mechanism, the only options are to disable the plugin entirely or accept that all session content is captured. A lightweight configuration file, absent by default, lets users define include/exclude rules that the ingestion pipeline consults on each pass — with no restart required and no change to the default all-capture behavior.

## Acceptance Criteria

- AC-1: Given no scope config file exists at `~/.claude/plugins/ephemeris/scope.yaml`, when an ingestion pass runs, then all session content is ingested without error.
- AC-2: Given a valid scope config with one or more `include` path patterns, when an ingestion pass runs, then only sessions whose project path matches at least one include pattern are ingested.
- AC-3: Given a valid scope config with one or more `exclude` path patterns, when an ingestion pass runs, then sessions whose project path matches any exclude pattern are not ingested, even if they also match an include pattern.
- AC-4: Given a scope config is present and valid, when the file is edited and the next ingestion pass runs (without restarting Claude Code or the plugin), then the updated rules are applied to that pass.
- AC-5: Given a scope config file exists but contains invalid YAML or an unrecognized schema, when an ingestion pass runs, then the plugin logs a descriptive parse error, falls back to all-capture behavior, and does not crash.
- AC-6: Given a scope config with an `exclude` rule matching a session's project path, when the ingestion pass processes that session, then no content from that session appears in the wiki store.
- AC-7: Given a scope config with only an `include` rule for project path `A`, when an ingestion pass encounters a session from project path `B` (not in any include), then the session from `B` is not ingested.

## Architecture Recommendation

**Config file location:** `~/.claude/plugins/ephemeris/scope.yaml`

Co-located with the plugin so no additional lookup path is needed. Absence of the file is the zero-config default; the ingestion pipeline treats a missing file as "include everything."

**Config file format (YAML):**

```yaml
# scope.yaml — all fields optional; absence = include everything
include:
  - "/Users/alice/projects/work/**"
  - "/Users/alice/projects/oss/**"
exclude:
  - "/Users/alice/projects/work/secrets/**"
  - "**/.private/**"
```

- `include`: list of glob patterns matched against the session's `cwd` (working directory). If present and non-empty, only matching sessions are ingested.
- `exclude`: list of glob patterns. Matching sessions are always skipped, regardless of `include`.
- Both lists default to empty (no filtering).
- Patterns follow standard glob semantics (`**` for any path segment depth).

**Evaluation logic:**

```
function isInScope(sessionCwd, config):
  if config.include is non-empty AND sessionCwd does not match any include pattern:
    return false
  if sessionCwd matches any exclude pattern:
    return false
  return true
```

`exclude` always wins over `include`.

**Hot-reload mechanism:** The ingestion hook reads and parses `scope.yaml` at the start of each invocation. No caching between runs. Because each hook invocation is a fresh process, the file is always read from disk — hot-reload is structural, not a feature that needs implementation.

**Pipeline integration point:** The scope check runs in `hooks/post-session.js` and `hooks/pre-compact.js` immediately after the payload is parsed and before any content is written to the wiki store. Sessions that fail the scope check are silently skipped (no wiki write, no error surfaced to user).

**Error handling:** Any YAML parse error or schema validation failure is written to the plugin's log file (`~/.claude/plugins/ephemeris/ephemeris.log`) at `WARN` level and execution continues with all-capture behavior.

## TDD Plan

**Step 1 — Scope config parser**
- RED: write tests for `lib/scope-config.js`: (a) returns `{include:[], exclude:[]}` when file is absent; (b) parses valid YAML and returns correct arrays; (c) returns default config and emits a warning when YAML is invalid.
- GREEN: implement `lib/scope-config.js` to satisfy all three cases.
- REFACTOR: extract glob list normalization (trim, filter empty strings) into a helper.

**Step 2 — `isInScope` predicate**
- RED: write unit tests for `lib/is-in-scope.js` covering: empty config (always true), include-only match, include-only non-match, exclude-only match, exclude wins over include, both lists empty.
- GREEN: implement `isInScope(sessionCwd, config)` using a glob-matching library (e.g., `minimatch`).
- REFACTOR: consolidate repeated pattern-matching calls.

**Step 3 — Integration with ingestion hook**
- RED: write an integration test that invokes `hooks/post-session.js` with a payload whose `cwd` matches an exclude rule in a temp `scope.yaml`; assert the wiki store receives no write for that session.
- GREEN: add scope-check call in the hook before the wiki write path.
- REFACTOR: verify the scope-check call site reads cleanly and has no duplication with the pre-compact hook.

**Step 4 — Hot-reload verification**
- RED: write a test that (a) invokes the hook with an empty scope config → content is written; (b) writes an exclude rule to the config file; (c) invokes the hook again with the same session → no content written; all without restarting any process.
- GREEN: confirm the file-read-per-invocation approach satisfies the test without additional code.
- REFACTOR: none expected; document the hot-reload guarantee in a code comment.
