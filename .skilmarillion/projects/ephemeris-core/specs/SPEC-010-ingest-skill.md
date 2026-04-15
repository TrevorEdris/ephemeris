# SPEC-010: Ingest Skill — Agent-Driven Body

**Feature ID:** P3-B
**Size:** MEDIUM
**Risk:** MEDIUM (runtime behavior change + ingestion quality risk)
**Status:** DRAFT — awaiting approval
**Depends on:** SPEC-009 merged (stubs in place, infrastructure ready, `~/.claude/ephemeris/default-schema.md` bootstrapped by hooks)
**Parallel with:** SPEC-011 (query skill body) — no dependency between them.

## Problem Statement

SPEC-009 replaced `commands/ingest.md` with a stub that emits a "pending SPEC-010" message. Hooks continue to stage session transcripts into `~/.claude/ephemeris/staging/pending/*.jsonl`, but no wiki updates happen. This SPEC replaces the stub body with full agent instructions the live Claude Code session follows to ingest staged transcripts, merge extracted content into the local wiki, and drain the pending queue.

The session uses its own model — no subprocess, no API key, no outbound HTTPS. All file work uses Claude Code's native tool palette (`Read`, `Write`, `Glob`, `Bash: mv`).

## Non-Goals

- No model-client abstraction. Session is the model.
- No helper CLIs. Infrastructure already decided in SPEC-009.
- No change to the schema content, file format, page layout, or wiki directory structure.
- No change to capture pipeline, hooks, or `StageWriter`.

## Acceptance Criteria

### Skill Body

- **AC-1:** `commands/ingest.md` frontmatter unchanged from SPEC-009 stub except `description` updated to: `Ingest pending Claude Code sessions into the local wiki using the current session's model.` `argument-hint` stays `"[<session-id>]"`. `allowed-tools` stays `[Bash, Read, Write, Glob]`.
- **AC-2:** Body replaces the SPEC-009 stub sentinel with ordered agent instructions matching the **Skill Contract** below. Zero occurrences of `python3 -m ephemeris.*` or any subprocess call to deleted Python modules.
- **AC-3:** Body explicitly instructs the session to resolve the schema via the 4-step precedence chain: `$EPHEMERIS_SCHEMA_PATH` → `~/.claude/ephemeris/schema.md` → `<wiki_root>/SCHEMA.md` → `~/.claude/ephemeris/default-schema.md`.
- **AC-4:** Body explicitly instructs the session to `Glob` `~/.claude/ephemeris/staging/pending/*.jsonl` (honoring `$EPHEMERIS_STAGING_ROOT` if set).
- **AC-5:** Body explicitly instructs the session to process each pending JSONL: `Read` transcript → extract decisions/entities/topics per schema → for each page, `Glob` existing, `Read` if found, merge inline, `Write` back; if new, `Write` new file per schema template.
- **AC-6:** Body explicitly instructs the session to mark consumed via `Bash: mv` from `pending/` to `processed/` only after all pages for that session have been successfully written. If any `Write` fails, the session skips the `mv` and the JSONL stays in `pending/` for retry on the next run.
- **AC-7:** Body instructs the session to emit a one-line summary per session on completion: `<session-id>: <N> pages created, <M> pages updated, <K> contradictions flagged`.
- **AC-8:** If `$ARGUMENTS` is non-empty, body instructs the session to filter pending sessions to the matching session-id and emit `No staged session matches <id>.` + stop if zero matches.
- **AC-9:** If the pending directory is empty (with no `$ARGUMENTS`), body instructs the session to emit `No pending sessions to ingest.` and stop.

### Behavior

- **AC-10:** Running `/ephemeris:ingest` on a fresh install with `unset ANTHROPIC_API_KEY` and at least one fixture staged session produces at least one wiki page in `~/.claude/ephemeris/wiki/` AND moves the fixture JSONL from `pending/` to `processed/`. Zero outbound network requests from the plugin.
- **AC-11:** Running `/ephemeris:ingest <session-id>` with a known-staged session-id processes only that one session.
- **AC-12:** Running `/ephemeris:ingest` twice in a row processes the queued sessions on the first run and emits `No pending sessions to ingest.` on the second (idempotence via the `pending/` → `processed/` move).
- **AC-13:** Interrupting the skill mid-run (crash simulation) leaves the in-progress session's JSONL in `pending/`. The next run picks it up and re-processes. Pages that were successfully `Write`-ten before the crash are not corrupted (single-file atomic writes via native `Write` tool).

### Canary Eval (pre-merge manual gate)

- **AC-14:** Run the skill manually against 10 fixture staged JSONLs drawn from real Claude Code sessions of varying length (5 short, 3 medium, 2 long). For each:
  - At least one wiki page is written.
  - Written pages follow the shipped schema (naming convention, required sections).
  - Extracted content is recognizably derived from the transcript (not hallucinated).
  - Merge preserves prior page content when merging into existing pages.
- **AC-15:** Document the canary eval results in the SPEC-010 PR description: 10/10 pass or a specific list of failures with root cause. Do not merge if <9/10 pass.

## Skill Contract

### `commands/ingest.md`

```markdown
---
description: Ingest pending Claude Code sessions into the local wiki using the current session's model.
argument-hint: "[<session-id>]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /ephemeris:ingest

Process pending Claude Code session transcripts into the local wiki. All model
reasoning happens in this session — no subprocess, no API key, no outbound calls.

## Instructions

### 1. Resolve the schema

Try each of these in order and use the first that exists and is non-empty. Hold
the schema text in working memory for this run only.

1. `$EPHEMERIS_SCHEMA_PATH` — check with `Bash: echo "$EPHEMERIS_SCHEMA_PATH"`;
   if non-empty, `Read` that path.
2. `~/.claude/ephemeris/schema.md` — user personal override.
3. `<wiki_root>/SCHEMA.md` where `<wiki_root>` is `$EPHEMERIS_WIKI_ROOT` (or
   `~/.claude/ephemeris/wiki` if unset) — per-wiki override.
4. `~/.claude/ephemeris/default-schema.md` — shipped default, bootstrapped on
   every hook fire.

### 2. List pending sessions

`Glob`: `~/.claude/ephemeris/staging/pending/*.jsonl` (or
`$EPHEMERIS_STAGING_ROOT/pending/*.jsonl` if the env var is set).

- If `$ARGUMENTS` is non-empty, filter to the session-id matching `$ARGUMENTS`.
  If zero matches, emit `No staged session matches <id>.` and stop.
- If the pending directory is empty, emit `No pending sessions to ingest.` and
  stop.

### 3. Process each pending session

For each JSONL path in the pending list:

a. `Read` the JSONL transcript.

b. Reason over the transcript against the schema. Extract the decisions,
   entities, and topics the schema defines. This is the model work this session
   does directly — no subprocess.

c. For each extracted page:
   - Compute the canonical filename per the schema:
     - Decisions → appended to `<wiki_root>/DECISIONS.md`
     - Topics → `<wiki_root>/topics/<kebab-case>.md`
     - Entities → `<wiki_root>/entities/<PascalCase>.md`
   - `Glob` `<wiki_root>/**/<canonical-name>` to check existence.
   - **If exists:** `Read` the page, merge the new content into the appropriate
     section (preserve all prior content; flag contradictions inline using the
     schema's contradiction marker), then `Write` the merged content back to
     the same path.
   - **If new:** build content from the schema's page template and `Write` it
     to the target path.
   - Append a citation to the page's `## Sessions` block: `> Source: [YYYY-MM-DD session-id]`.

d. **Mark consumed** only after all pages for this session have been
   successfully written: `Bash: mv <pending_path> <processed_path>` where
   `<processed_path>` is the same filename under `pending/`'s sibling
   `processed/` directory. Rename is atomic on same filesystem.

### 4. Error handling

- If any `Write` fails, stop processing the current session, do NOT run the
  `mv`, and continue to the next pending session. The JSONL stays in
  `pending/` and the next run retries it.
- If reasoning over a transcript produces zero extracted pages, still run the
  `mv` — the session was processed, it just had no wiki-worthy content. Emit
  `<session-id>: 0 pages (no extractable content)`.

### 5. Summary

After all sessions processed, emit one line per session:

`<session-id>: <N> pages created, <M> pages updated, <K> contradictions flagged`
```

## TDD Plan

SPEC-010 is dominated by a single-file rewrite (`commands/ingest.md`) whose body is prose instructions consumed by a running Claude Code session. There is no Python behavior to unit-test. Verification splits into three layers:

### RED — static guard tests

1. `tests/spec_010/test_ingest_skill_body.py`:
   - Parses `commands/ingest.md` frontmatter + body.
   - Asserts frontmatter has `description` mentioning "current session's model" (or similar — specific string match), `argument-hint: "[<session-id>]"`, `allowed-tools: [Bash, Read, Write, Glob]`.
   - Asserts body contains each of: "Resolve the schema", "Glob", "Read", "Write", "Bash: mv", schema precedence chain keywords (`$EPHEMERIS_SCHEMA_PATH`, `schema.md`, `SCHEMA.md`, `default-schema.md`).
   - Asserts body contains the SPEC-009 stub sentinel — **negated**. (Ensures the stub was actually replaced.)
   - Asserts body contains zero of: `python3 -m ephemeris`, `anthropic`, `ANTHROPIC_API_KEY`, `ephemeris.cli`.
   - **Fails after SPEC-009 merges** (stub sentinel still present).
2. `tests/spec_010/test_ingest_skill_error_handling.py`:
   - Asserts body contains the phrase "stays in `pending/`" or equivalent (the retry semantics the skill must tell the session to follow).
   - Asserts body contains a case for empty pending directory (`No pending sessions to ingest.`).
   - Asserts body contains a case for unknown session-id filter (`No staged session matches`).

### Canary eval — manual pre-merge gate (not automated)

Run the skill against 10 fixture staged JSONLs. Record pass/fail per AC-14. PR description must include the eval results before merge. <9/10 pass = do not merge.

Fixture JSONLs live under `tests/fixtures/staging/canary/` and are committed to the repo. They are real captured sessions with any PII redacted.

### GREEN

- Replace `commands/ingest.md` body per Skill Contract.
- Commit fixture JSONLs under `tests/fixtures/staging/canary/`.
- Run canary eval manually; paste results into PR.

### REFACTOR

- Review body for clarity; collapse redundant steps.
- Ensure every imperative instruction has a verb and a target ("`Read` the JSONL", not "JSONL should be read").

### Verification gate

- `python -m pytest -q` passes (all static guard tests green).
- Canary eval ≥ 9/10.
- Manual smoke: `unset ANTHROPIC_API_KEY`, fire `/ephemeris:ingest` against a known-staged fixture in a live Claude Code session, verify wiki page appears and JSONL moves to `processed/`.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Skill produces different (worse) wiki content than the old subprocess pipeline | High | Medium | Canary eval of 10 sessions, pre-merge gate at ≥ 9/10. Document drift in PR for future baseline. |
| Session forgets a step (e.g., skips the `mv`) because the instructions are not imperative enough | Medium | Medium | Body uses direct imperatives ("`Read` X", "`Write` Y") and numbered steps. Guard test asserts each required keyword is present. |
| Contradictions not flagged because schema instructions are ambiguous | Medium | Low | Schema already defines contradiction marker — inherited from SPEC-004 design. Canary eval will surface if it regresses. |
| Half-merged session on crash leaves some pages written, others not | Low | Low | Each `Write` is atomic. Session stays in `pending/` until fully processed. Next run re-processes — idempotent at the session level (not at the page level, but page-level merge is already idempotent because appends dedupe by citation). |
| Large transcripts exceed the session's attention budget | Medium | Medium | No chunking in this SPEC. If a canary session fails due to length, document it and defer chunking to a follow-up SPEC. Record which sessions succeed as baseline. |
| Session drifts from schema over time as model versions change | Low | Medium | Standing canary eval on every release (see Verification gate). If quality regresses, tighten the schema prose. |

## Traceability

| PRD Requirement | How this SPEC satisfies it |
|---|---|
| FR-001 "Automatic Post-Session Ingestion" | Capture pipeline (SPEC-002) + this SPEC's ingest skill + automatic trigger (future SPEC or manual trigger via `/ephemeris:ingest`). For now, ingestion is manual. |
| FR-004 "Incremental Wiki Updates" | AC-5 merge preserves prior content; AC-5 contradiction flagging. |
| FR-005 "Manual Ingest Trigger" | The skill IS the manual trigger. |
| NFR-001 "Ingestion uses the active session's model" | AC-1..AC-7 — session does all reasoning, no subprocess. |
| NFR-002 "Ingestion Latency < 60s for a 60-minute session" | Not formally tested in this SPEC. Canary eval notes wall-clock per session. |
| NFR-004 "Failure Isolation" | AC-13 + error handling section — crash mid-run leaves wiki intact, pending JSONL retries. |
| Principle P-1 "In-Session, Not Alongside" | AC-2 + AC-10 — zero subprocess, all tool-palette work. |

## Rollout

1. SPEC-009 merges first. Both commands become stubs. Capture pipeline still runs. Wiki stops updating. Pending queue grows.
2. SPEC-010 merges. First run of `/ephemeris:ingest` after merge drains the accumulated queue. User sees summary of backfilled sessions.
3. Users who ran `/ephemeris:ingest` between SPEC-009 and SPEC-010 merges saw the stub sentinel — no corruption risk, just a no-op with an explanatory message.

## Open Questions

1. Should the skill run the schema resolution check every run, or cache the schema between runs? Cache would optimize for repeated calls but the skill is short-lived (one slash command per invocation). Default: re-resolve every run. No perf concern at the scale of one `Read` per run.
2. Should the skill also handle `tests/fixtures/staging/canary/` as a real target when `$EPHEMERIS_STAGING_ROOT` points there, or should canary eval use a separate test harness? Default: honor `$EPHEMERIS_STAGING_ROOT` so canary runs against a scoped copy.
3. What is the contradiction marker syntax the schema defines? Confirm against `schema/default.md` before canary eval (should be inherited unchanged from the prior `DEFAULT_SCHEMA` text).
