# SPEC-001: Plugin Scaffolding + Hook Registration

**Feature ID:** P0-A
**Size:** SMALL
**Risk:** LOW
**Status:** IMPLEMENTED

## Problem Statement

Claude Code has no built-in mechanism to automatically capture and persist session knowledge. Users lose context from every session unless they manually document it. The ephemeris plugin addresses this by hooking into Claude Code's lifecycle events, but before any ingestion logic can exist, the plugin itself must be installable and its hooks must be registered and reachable. Without a correct manifest and directory structure, Claude Code will not recognize the plugin, and no subsequent feature can be built on top of it.

## Acceptance Criteria

- AC-1: Given a fresh environment with no prior ephemeris configuration, when the plugin is installed to `~/.claude/plugins/ephemeris/`, then Claude Code recognizes the plugin and loads it without errors or warnings.
- AC-2: Given the plugin is installed, when Claude Code starts a session, then no user configuration is required for the plugin to be active.
- AC-3: Given the plugin is installed and a session ends, when Claude Code fires the `Stop` hook, then the ephemeris post-session hook entry point is invoked.
- AC-4: Given the plugin is installed and a context compaction occurs, when Claude Code fires the `PreCompact` hook, then the ephemeris pre-compaction hook entry point is invoked.
- AC-5: Given the `Stop` hook fires, when the hook entry point runs, then the JSON payload provided by Claude Code is accessible to the hook process.
- AC-6: Given the `PreCompact` hook fires, when the hook entry point runs, then the JSON payload provided by Claude Code is accessible to the hook process.
- AC-7: Given either hook fires, when the hook entry point completes without implementing any ingestion logic, then Claude Code session behavior is unaffected and no errors are surfaced to the user.

## Architecture Recommendation

Follow the Claude Code plugin convention: all plugin files live under `~/.claude/plugins/ephemeris/`. The manifest file (`plugin.yaml`) declares the plugin identity, the hooks it registers, and the locations of skills and agents.

Recommended directory layout:

```
~/.claude/plugins/ephemeris/
├── plugin.yaml               # manifest: name, version, hooks, skills, agents
├── hooks/
│   ├── post-session.js       # entry point for Stop hook
│   └── pre-compact.js        # entry point for PreCompact hook
├── skills/                   # reserved for future skill markdown files
└── agents/                   # reserved for future agent markdown files
```

`plugin.yaml` registers the hooks by type and file path:

```yaml
name: ephemeris
version: 0.1.0
hooks:
  - type: Stop
    file: hooks/post-session.js
  - type: PreCompact
    file: hooks/pre-compact.js
skills: []
agents: []
```

Each hook file reads stdin, parses the JSON payload, logs receipt (as a no-op stub), and exits 0. This satisfies the wiring contract without any ingestion logic.

```js
// hooks/post-session.js
process.stdin.resume();
const chunks = [];
process.stdin.on('data', (chunk) => chunks.push(chunk));
process.stdin.on('end', () => {
  const payload = JSON.parse(Buffer.concat(chunks).toString());
  // stub: ingestion logic not yet implemented
  process.exit(0);
});
```

The `pre-compact.js` hook follows the identical pattern. Both hooks must exit 0 to avoid interrupting Claude Code's normal flow.

No environment variables, config files, or user prompts are required for the plugin to load and both hooks to fire.

## TDD Plan

**Step 1 — Manifest schema validation**
- Test name: `plugin.yaml contains required fields`
- Asserts: the manifest file exists at the expected path, parses as valid YAML, and contains `name`, `version`, and `hooks` keys with at least two hook entries (`Stop` and `PreCompact`) each referencing an existing file path.
- RED: write the test before creating `plugin.yaml` — it fails because the file does not exist.
- GREEN: create `plugin.yaml` with the fields above — test passes.

**Step 2 — Hook files exist and are executable**
- Test name: `hook entry points exist and exit cleanly on empty stdin`
- Asserts: `hooks/post-session.js` and `hooks/pre-compact.js` exist; when invoked with an empty stdin (or a minimal valid JSON payload `{}`), each process exits with code 0 and produces no output to stderr.
- RED: write the test before creating the hook files — fails with file-not-found.
- GREEN: create both stub hook files as described in Architecture — test passes.

**Step 3 — Payload is accessible**
- Test name: `hook parses stdin payload without throwing`
- Asserts: when either hook is invoked with a JSON payload on stdin (e.g., `{"session_id":"test-123","transcript":[]}`), the process parses it without throwing and exits 0.
- RED: remove or corrupt the JSON.parse call — test detects non-zero exit or stderr output.
- GREEN: restore correct stdin parsing — test passes.

**Step 4 — Plugin directory structure is complete**
- Test name: `plugin directory contains all required entries`
- Asserts: `skills/` and `agents/` directories exist under the plugin root (even if empty), satisfying the manifest's declared structure.
- RED: write the test before creating the directories — fails.
- GREEN: create the empty directories — test passes.

**Refactor**
- Extract the stdin-read-and-parse pattern into a shared `lib/read-payload.js` module consumed by both hooks.
- Re-run all four tests — all remain GREEN.
- Verify no behavior change: hook processes still exit 0 with no stderr output.
