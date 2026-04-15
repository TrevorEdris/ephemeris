# SPEC-009: Subprocess Pipeline Rip + Schema Bootstrap

**Feature ID:** P3-A
**Size:** MEDIUM
**Risk:** HIGH (blast radius — many deletions; low runtime risk — pure infrastructure)
**Status:** DRAFT v3 — awaiting approval
**Depends on:** P0-A through P2-B (all prior SPECs merged)
**Supersedes behavior of:** SPEC-003 (model invocation), SPEC-004 (merge pipeline), SPEC-008 (schema loader Python API)
**Followed by:** SPEC-010 (ingest skill body) and SPEC-011 (query skill body), both of which depend on SPEC-009 merged.

**v3 change (2026-04-15):** split from v2. SPEC-009 now covers **only** the rip + infrastructure: delete all subprocess pipeline Python, ship `schema/default.md`, wire hook-side bootstrap copy, replace both slash commands with **stub skills** that emit a "pending SPEC-0XX" message. SPEC-010 replaces the ingest stub with a full agent-instruction body. SPEC-011 replaces the query stub with a full agent-instruction body. Split exists to shrink PR blast radius and allow SPEC-010/011 to land in parallel.

## Problem Statement

Phase 0–2 shipped a plugin that violates its own PRD. NFR-001 and NFR-005 require zero outbound network calls and zero additional API keys; the plugin installs under these constraints but the actual ingest/query runtime does the opposite. `ephemeris/model.py` instantiates `anthropic.Anthropic()`, requires `ANTHROPIC_API_KEY`, and issues HTTPS calls to `api.anthropic.com`. `commands/ingest.md` and `commands/query.md` are bash wrappers around `python3 -m ephemeris.ingest` / `python3 -m ephemeris.query`, which spawn a subprocess that instantiates the SDK. The running Claude Code session — the whole reason hooks exist — does none of the model work.

Point of divergence: SPEC-003 line 63 correctly stated *"call the active Claude model via the Claude Code plugin API (tool call or agent invocation). No `fetch`, no `axios`, no external endpoints."* SPEC-003 line 109 then introduced `modelClient` as an injected dependency without defining the concrete production form. The implementer chose the path of least resistance (Anthropic SDK), the `FakeModelClient` abstraction hid the violation from every test, and review never challenged it.

This SPEC rips the subprocess model pipeline out and lays the infrastructure (shipped default schema + hook-side bootstrap) that the follow-up skill SPECs need. SPEC-010 and SPEC-011 write the actual agent-instruction bodies. No deprecation, no backwards compatibility — MVP rip-and-replace.

## Scope

**In scope:**
- Delete all Python modules that exist only to serve the subprocess pipeline.
- Ship `schema/default.md` at plugin root (replaces `DEFAULT_SCHEMA` Python constant).
- Add `capture.bootstrap_default_schema()` + wire it into both hook runners.
- Replace `commands/ingest.md` and `commands/query.md` with **stub skills** — valid frontmatter, body emits a one-line "pending SPEC-0XX" message, no subprocess calls.
- Remove `anthropic` from `pyproject.toml`.
- Strip `ANTHROPIC_API_KEY` from `README.md`.
- Delete every test module that targets removed code.
- Add guard tests (import, symbol references, README, pyproject, schema file, bootstrap).

**Explicitly out of scope (delegated):**
- Full agent-instruction body for `commands/ingest.md` → **SPEC-010 (P3-B)**.
- Full agent-instruction body for `commands/query.md` → **SPEC-011 (P3-C)**.
- Canary eval of ingestion quality → **SPEC-010**.
- Canary eval of query grounding → **SPEC-011**.

## Non-Goals

- No schema content redesign. Default schema *text* unchanged — byte-for-byte copy of the prior `DEFAULT_SCHEMA` Python constant.
- No migration tooling. Existing wikis built with subprocess path are byte-compatible. Pending staged JSONL queues up during the SPEC-009 → SPEC-010 gap and is processed when SPEC-010 lands.
- No model-client abstraction replacement. Session *is* the model — no successor to `ModelClient`.
- No helper CLI surface (`ephemeris.cli` is not created). Claude Code's native `Write` tool is atomic (`anthropics/claude-code#15832`); `Bash: mv` is atomic; the session is a trusted actor so path traversal defense is unnecessary.

## Acceptance Criteria

### Rip

- **AC-1:** `ephemeris/model.py` deleted. No file in tree imports `anthropic` or references `AnthropicModelClient`, `FakeModelClient`, or `ModelClient` Protocol.
- **AC-2:** `ephemeris/prompts.py` deleted. No references to `build_system_prompt`, `build_user_prompt`, `build_merge_prompt`.
- **AC-3:** `ephemeris/merge.py` deleted. No references to `run_merge`.
- **AC-4:** `ephemeris/ingest.py` deleted. Model-path code, `list_pending_sessions`, `IngestSummary` all gone.
- **AC-5:** `ephemeris/query.py` deleted. `run_query`, `build_grounded_prompt`, `FilesystemRetriever`, `format_citations` all gone.
- **AC-6:** `ephemeris/wiki.py` deleted. `_atomic_write_text` + `_sanitize_page_name` gone.
- **AC-7:** `ephemeris/schema.py` deleted. `DEFAULT_SCHEMA` and `resolve_schema` no longer exist in Python form.
- **AC-8:** `pyproject.toml` no longer lists `anthropic` as a runtime dependency.
- **AC-9:** `README.md` no longer contains `ANTHROPIC_API_KEY`. Env var row dropped. Installation section shows only `/plugin marketplace add` + `/plugin install`. Dev section no longer mentions `AnthropicModelClient`.

### Ship + Bootstrap

- **AC-10:** `schema/default.md` exists at plugin root. Content matches the prior `DEFAULT_SCHEMA` constant byte-for-byte (after Python string-literal unescaping).
- **AC-11:** `ephemeris/capture.py` exports `bootstrap_default_schema() -> None`. Contract:
  - Source: `Path(__file__).parent.parent / "schema" / "default.md"`
  - Dest: `Path("~/.claude/ephemeris/default-schema.md").expanduser()`
  - Copies (temp + `os.replace`) when dest missing OR `source.stat().st_mtime > dest.stat().st_mtime`.
  - No-op when dest exists and is equal-or-newer.
  - Logs diagnostic on failure; never raises.
- **AC-12:** `hooks/post_session.py` handler calls `bootstrap_default_schema()` before any staging work. Same for `hooks/pre_compact.py`.
- **AC-13:** After a single hook fire on a fresh install, `~/.claude/ephemeris/default-schema.md` exists and its content matches `<plugin_root>/schema/default.md` byte-for-byte. Fault-injection test: delete the destination file between hook fires; the next fire restores it.

### Stub Commands

- **AC-14:** `commands/ingest.md` is a **stub skill**. Frontmatter declares `description`, `argument-hint: "[<session-id>]"`, `allowed-tools: [Bash, Read, Write, Glob]`. Body is a single instruction line telling the session to emit exactly: `/ephemeris:ingest: full ingest implementation pending in SPEC-010 (P3-B). Hooks continue to stage sessions; any queued sessions will be processed once SPEC-010 lands.` No subprocess calls. No wiki writes. No transcript reads.
- **AC-15:** `commands/query.md` is a **stub skill**. Frontmatter declares `description`, `argument-hint: "<question>"`, `allowed-tools: [Read, Glob, Grep]`. Body is a single instruction line telling the session to emit exactly: `/ephemeris:query: full query implementation pending in SPEC-011 (P3-C). Wiki query will work once SPEC-011 lands.` No wiki reads.
- **AC-16:** Neither stub contains any occurrence of `python3 -m ephemeris.*`, `anthropic`, or `ANTHROPIC_API_KEY`.

### Verify

- **AC-17:** Capture pipeline unchanged otherwise. `tests/spec_001/**` and `tests/spec_002/**` pass. StageWriter journal/rollback tests pass.
- **AC-18:** Every test that imports `FakeModelClient`, `AnthropicModelClient`, `build_system_prompt`, `build_grounded_prompt`, `run_merge`, `list_pending_sessions`, `_atomic_write_text`, `_sanitize_page_name`, `resolve_schema`, `DEFAULT_SCHEMA`, `FilesystemRetriever`, `format_citations`, or `run_query` is deleted.
- **AC-19:** Full suite passes with `unset ANTHROPIC_API_KEY`. Expected count drops materially from 280.
- **AC-20:** Guard tests added under `tests/spec_009/`:
  - `test_no_anthropic_import.py` — AST walk of every `ephemeris/*.py` + `hooks/*.py`; asserts `anthropic` appears in no import. Augmented with regex scan for the literal string `"anthropic"` to catch lazy imports.
  - `test_commands_are_stubs.py` — asserts both slash command files have valid frontmatter (description, argument-hint, allowed-tools), body contains the exact pending-SPEC sentinel string, body contains zero `python3 -m ephemeris.*` calls.
  - `test_pyproject_no_anthropic.py` — parses `pyproject.toml`, asserts `anthropic` not in `project.dependencies`.
  - `test_readme_no_api_key.py` — asserts `ANTHROPIC_API_KEY` string absent from `README.md`.
  - `test_default_schema_file_exists.py` — asserts `<plugin_root>/schema/default.md` exists and is non-empty.
  - `test_no_deleted_symbol_references.py` — source-tree grep for 14 deleted symbols; zero matches outside SPEC docs.
  - `test_schema_bootstrap.py` — five cases: copies-when-missing, refreshes-when-stale, noop-when-fresh, restores-after-deletion, failure-is-non-fatal.

## Architecture

### Before (wrong)

```
/ephemeris:ingest           (bash wrapper)
  └── subprocess: python3 -m ephemeris.ingest
        └── AnthropicModelClient
              └── anthropic.Anthropic()
                    └── HTTPS → api.anthropic.com   ← VIOLATION
```

### After SPEC-009 (this SPEC)

```
hook fire (post_session / pre_compact)
  ├── bootstrap_default_schema()
  │     └── copy <plugin_root>/schema/default.md → ~/.claude/ephemeris/default-schema.md
  └── (existing) stage transcript JSONL

/ephemeris:ingest           (stub skill)
  └── session emits: "/ephemeris:ingest: full ingest implementation pending in SPEC-010..."

/ephemeris:query            (stub skill)
  └── session emits: "/ephemeris:query: full query implementation pending in SPEC-011..."
```

### After SPEC-010 + SPEC-011 (end-state, for context only)

```
/ephemeris:ingest           (agent instructions — SPEC-010)
  └── live session Read/Glob/Write against staged transcripts + schema

/ephemeris:query            (agent instructions — SPEC-011)
  └── live session Glob/Grep/Read against wiki
```

### Files deleted (Python)

| Path | Reason |
|---|---|
| `ephemeris/model.py` | SDK client surface |
| `ephemeris/prompts.py` | Prompt builders only used by subprocess pipeline |
| `ephemeris/merge.py` | Model-driven merge |
| `ephemeris/ingest.py` | Model-invocation + `list_pending_sessions` |
| `ephemeris/query.py` | `run_query`, retrieval, citation format |
| `ephemeris/wiki.py` | Atomic write helpers (native `Write` is atomic) + sanitization (no untrusted path sink) |
| `ephemeris/schema.py` | `DEFAULT_SCHEMA` migrates to file; `resolve_schema` becomes skill instructions |

### Files deleted (tests)

| Path | Reason |
|---|---|
| `tests/spec_003/test_*model*.py` | Targets deleted `model.py` |
| `tests/spec_003/test_*prompt*.py` | Targets deleted `prompts.py` |
| `tests/spec_003/test_*ingestion*pipeline*.py` | Targets deleted model-path ingest |
| `tests/spec_004/test_merge*.py` | Targets deleted `merge.py` |
| `tests/spec_005/test_cli_extension.py` | Targets deleted `ephemeris.ingest` CLI |
| `tests/spec_005/test_pages_tracking.py` | Targets deleted `PageResult` / ingestion counts |
| `tests/spec_006/test_*.py` (all using FakeModelClient) | Targets deleted query pipeline |
| `tests/spec_008/test_schema_integration.py` | Targets deleted `resolve_schema` Python API |
| `tests/spec_008/test_schema_loader.py` | Loader deleted — no Python API remains |
| Any other `tests/**/test_*.py` that import deleted symbols | Same |

### Files modified

| Path | Change |
|---|---|
| `ephemeris/capture.py` | **Add** `bootstrap_default_schema()` function |
| `hooks/post_session.py` | **Add** one-line call to `bootstrap_default_schema()` at top of handler |
| `hooks/pre_compact.py` | Same |
| `ephemeris/__init__.py` | Remove any re-exports of deleted symbols |
| `pyproject.toml` | Remove `anthropic>=0.20.0`. Runtime deps shrink to stdlib-only. |
| `README.md` | Drop `ANTHROPIC_API_KEY` + env var row + `AnthropicModelClient` mention; redraw architecture diagram; add one sentence on bootstrap behavior |
| `commands/ingest.md` | Replace subprocess wrapper with **stub skill** (see AC-14) |
| `commands/query.md` | Replace subprocess wrapper with **stub skill** (see AC-15) |

### Files kept (unchanged unless noted)

| Path | Purpose | Change |
|---|---|---|
| `ephemeris/stage.py` | `StageWriter` + `recover_orphans` — hook-side crash safety | Unchanged |
| `ephemeris/transcript.py` | JSONL parsing for hooks | Unchanged |
| `ephemeris/scope.py` | Scope gate for hooks | Unchanged |
| `ephemeris/log.py` | Diagnostic logger | Unchanged |
| `ephemeris/exceptions.py` | Exception types | Unchanged |
| `tests/spec_001/**` | Plugin scaffolding | Unchanged |
| `tests/spec_002/**` | Capture hook tests | Unchanged |
| `tests/spec_007/**` | Scope config tests | Unchanged |

### Files added

| Path | Purpose |
|---|---|
| `schema/default.md` | Shipped default wiki schema. Replaces `DEFAULT_SCHEMA` Python constant. |
| `tests/spec_009/test_no_anthropic_import.py` | AST walk — no runtime module imports `anthropic` |
| `tests/spec_009/test_commands_are_stubs.py` | Both slash commands are stubs with required frontmatter + sentinel body + zero subprocess calls |
| `tests/spec_009/test_pyproject_no_anthropic.py` | `anthropic` not in `[project.dependencies]` |
| `tests/spec_009/test_readme_no_api_key.py` | `ANTHROPIC_API_KEY` absent from README |
| `tests/spec_009/test_default_schema_file_exists.py` | `schema/default.md` exists and is non-empty |
| `tests/spec_009/test_no_deleted_symbol_references.py` | Source tree grep for 14 deleted symbols returns zero |
| `tests/spec_009/test_schema_bootstrap.py` | Five bootstrap cases per AC-13 |

## Stub Skill Contracts

### `commands/ingest.md` (stub)

```markdown
---
description: Ingest pending Claude Code sessions into the local wiki (pending SPEC-010).
argument-hint: "[<session-id>]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /ephemeris:ingest

Emit exactly the following line and stop:

`/ephemeris:ingest: full ingest implementation pending in SPEC-010 (P3-B). Hooks continue to stage sessions; any queued sessions will be processed once SPEC-010 lands.`
```

### `commands/query.md` (stub)

```markdown
---
description: Answer a question from the local wiki (pending SPEC-011).
argument-hint: "<question>"
allowed-tools:
  - Read
  - Glob
  - Grep
---

# /ephemeris:query

Emit exactly the following line and stop:

`/ephemeris:query: full query implementation pending in SPEC-011 (P3-C). Wiki query will work once SPEC-011 lands.`
```

## Why No Helper CLIs

Earlier drafts proposed five helper CLIs. All dropped:

| Proposed CLI | Why dropped |
|---|---|
| `list-pending` | Session uses `Glob`. One tool call. |
| `resolve-schema` | Default schema moves to `schema/default.md` on disk; bootstrap copies it to a stable user-space path; `Read` handles precedence. |
| `wiki-write` | Native `Write` is atomic via temp+rename (`anthropics/claude-code#15832`). Session is trusted actor — no untrusted path sink. Single-file ops — no multi-file transaction. |
| `recover-orphans` | Only existed because `wiki-write` had a journal. No journal, no orphans. Hook-side `StageWriter` still uses its own journal — unchanged. |
| `mark-consumed` | `Bash: mv` is atomic on same filesystem. One line. |

Zero Python CLIs. Hook-side Python is unchanged except for the `bootstrap_default_schema()` addition.

## TDD Plan

### RED — write failing tests first

1. `test_no_anthropic_import.py` — AST walk; **fails today** (`model.py` imports it).
2. `test_commands_are_stubs.py` — asserts stub frontmatter + sentinel body + zero subprocess calls. **Fails today** (both commands are subprocess wrappers).
3. `test_pyproject_no_anthropic.py` — **fails today**.
4. `test_readme_no_api_key.py` — **fails today**.
5. `test_default_schema_file_exists.py` — **fails today** (file does not exist).
6. `test_no_deleted_symbol_references.py` — **fails today**.
7. `test_schema_bootstrap.py` (five cases) — **fails today** (`bootstrap_default_schema()` does not exist).

### GREEN

- Create `schema/default.md` byte-equal to prior `DEFAULT_SCHEMA` constant.
- Implement `capture.bootstrap_default_schema()` per AC-11 contract.
- Wire `bootstrap_default_schema()` into both hook runners.
- Delete `ephemeris/model.py`, `prompts.py`, `merge.py`, `ingest.py`, `query.py`, `wiki.py`, `schema.py`.
- Delete every test module listed in the deletions table.
- Replace `commands/ingest.md` and `commands/query.md` with stubs per Stub Skill Contracts.
- Remove `anthropic>=0.20.0` from `pyproject.toml`.
- Edit `README.md`: drop `ANTHROPIC_API_KEY`, drop env var row, redraw architecture diagram, remove `AnthropicModelClient` mention, add one sentence on bootstrap-on-hook behavior.

### REFACTOR

- Verify no dead imports in `ephemeris/` or `hooks/`.
- Verify `ephemeris/__init__.py` re-exports nothing deleted.
- Run `python -m pytest -q`; confirm green.
- Diff `schema/default.md` against prior `DEFAULT_SCHEMA` — byte-identical.

### Verification gate

- `python -m pytest -q` passes.
- `rg -n "anthropic" ephemeris/ hooks/ tests/ pyproject.toml` returns zero.
- `rg -n "ANTHROPIC_API_KEY" .` returns matches only in session docs + this SPEC.
- `rg -n "python3 -m ephemeris\." commands/` returns zero.
- Manual smoke: install plugin on fresh machine with `unset ANTHROPIC_API_KEY`, run a Claude Code session, verify hook fires successfully and `~/.claude/ephemeris/default-schema.md` appears. `/ephemeris:ingest` and `/ephemeris:query` emit their stub sentinels.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AST import scan misses a lazy import (`importlib.import_module("anthropic")`) | Low | Medium | Dual-layer guard: AST walk + regex scan for literal string `"anthropic"`. |
| Default schema markdown file drifts from `DEFAULT_SCHEMA` constant during the copy | Medium | Low | Copy byte-for-byte; commit diff review; `test_default_schema_file_exists` asserts non-empty (weak check; real check is the diff). |
| Hooks reference deleted modules by import chain (`ephemeris/__init__.py` re-exports `ModelClient`) | Medium | Medium | `test_no_deleted_symbol_references` scans whole tree including `__init__.py`. |
| User runs `/ephemeris:ingest` after SPEC-009 merges but before SPEC-010 — wiki stops updating, staged sessions queue up | Certain | Low | Stub sentinel message explains the state. Hooks still stage. SPEC-010 drains the queue on first run. Document the gap in SPEC-010's rollout section. |
| Claude Code `Write` atomicity assumption walked back in future version | Low | Medium | Documented in `Why No Helper CLIs`. If broken, re-introduce a single `wiki-write` helper. Not a concern until SPEC-010 actually uses `Write`. |
| Skill frontmatter `allowed-tools` is documentation-only | Medium | Low | Acceptable — no security boundary depends on it. |
| Existing pending staged JSONL incompatible | Low | Low | Format unchanged — same hooks stage the same JSONL shape. |

## Traceability

| PRD Requirement | How this SPEC satisfies it |
|---|---|
| Principle P-1 "In-Session, Not Alongside" | AC-1..AC-7 delete the subprocess SDK path entirely. Stub commands are tool-palette compliant. SPEC-010/011 complete the in-session rewrite. |
| Principle P-2 "Zero-Config — No Credentials Required" | AC-9 strips `ANTHROPIC_API_KEY` from README. No successor key introduced. |
| Principle P-3 "Local-First — No Network" | AC-1 + AC-20 standing import guard. |
| Principle P-4 "Transactional File Writes" | Hook-side `StageWriter` retained. Wiki-side writes deferred to SPEC-010 (uses native atomic `Write`). |
| NFR-001 "Ingestion uses the Claude model already active in the user's session" | AC-1..AC-7. SPEC-010 wires the actual model work. |
| NFR-001 target "Zero external network requests" | Guard tests. |
| NFR-005 target "Zero outbound network connections" | AC-1 + AC-20. |
| FR-002 "Zero-Config Install" | AC-9. |
| Scope Out "No additional API key" | Same. |

## Open Questions

1. Does `allowed-tools` in slash command frontmatter actually constrain tool access at runtime? Not blocking — no security boundary depends on it.
2. ~~`<plugin_root>` resolution at skill runtime~~ **RESOLVED 2026-04-15:** hook-side bootstrap copy to `~/.claude/ephemeris/default-schema.md`. Skill reads from stable user-space path.
3. Wiki page merge quality — deferred to SPEC-010 (canary eval).
4. Query grounding reliability — deferred to SPEC-011 (canary eval).
