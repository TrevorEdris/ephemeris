# SPEC-005: Manual Ingest Trigger

**Feature ID:** P1-A
**Size:** SMALL
**Risk:** LOW
**Status:** IMPLEMENTED
**Depends on:** P0-D (incremental update + contradiction detection)

## Problem Statement

The ephemeris wiki is updated automatically at the end of each Claude Code session, but users have no way to trigger ingestion on demand. This blocks workflows where the user wants to see wiki output mid-session, recover from a failed auto-trigger, or backfill sessions that were skipped. A slash command that runs the ingestion pipeline immediately and reports what changed closes this gap without requiring any changes to the underlying pipeline.

## Acceptance Criteria

- **AC-1:** Given one or more sessions have not yet been ingested, when the user runs `/ephemeris ingest`, then all pending sessions are processed and a summary is printed showing the count of pages created and pages updated.
- **AC-2:** Given ingestion is running, when the user is watching the output, then incremental progress feedback is displayed (e.g., per-session status lines) so the user can tell the command is active.
- **AC-3:** Given all sessions have already been ingested, when the user runs `/ephemeris ingest`, then the command exits cleanly with a message indicating no pending sessions were found and zero pages are reported as created or updated.
- **AC-4:** Given the user runs `/ephemeris ingest` twice in succession on the same set of sessions, when the second run completes, then the wiki contains no duplicate pages or duplicate content sections, and the second run reports zero pages created and zero pages updated.
- **AC-5:** Given the user provides a specific session identifier as an argument (e.g., `/ephemeris ingest <session-id>`), when the command runs, then only that session is processed and the summary reflects only that session's changes.
- **AC-6:** Given a session ingestion fails partway through, when the command finishes, then successfully processed sessions are reflected in the wiki, the failed session is flagged in the output with an error reason, and the wiki is left in a consistent state.
- **AC-7:** Given the ingestion pipeline (P0-D) reports a contradiction, when `/ephemeris ingest` encounters it, then the contradiction is surfaced in the completion summary so the user is aware without the command itself failing.

## Architecture Recommendation

The slash command is defined as a markdown skill file at `skills/ingest.md` inside the plugin. It is invoked as `/ephemeris ingest` or `/ephemeris:ingest` in the Claude Code UI.

The skill file instructs Claude to call the shared ingestion pipeline entry point from P0-C/D — no new ingestion logic lives in this skill. The skill's sole responsibilities are:

1. **Session resolution** — determine which sessions are pending (delegate to the pipeline's session-state store) or parse a session ID passed as an argument.
2. **Progress feedback** — emit a status line per session as it is processed (e.g., `[1/3] Ingesting session 2026-04-14_foo...`). This can be `console.log` / stdout writes flushed incrementally; no streaming protocol is needed.
3. **Summary output** — after all sessions complete, print a structured summary block: sessions processed, pages created, pages updated, contradictions flagged, errors encountered.

Idempotency is enforced entirely by the P0-D pipeline (content-hash checks before writing). The slash command does not need its own deduplication logic; running it twice simply results in the pipeline finding no diff on the second pass.

## TDD Plan

### RED — write failing tests first

1. **`ingest_command_processes_pending_sessions`** — stub the pipeline, assert it is called for each session returned by the pending-sessions query, assert summary counts match pipeline return values.
2. **`ingest_command_targeted_session`** — pass a session ID argument, assert pipeline is called exactly once with that session ID only.
3. **`ingest_command_no_pending_sessions`** — stub pipeline to return empty pending list, assert exit is clean and summary reports zeros.
4. **`ingest_command_idempotent`** — run command twice against the same sessions; on the second run stub pipeline to return `{created: 0, updated: 0}`; assert wiki state is unchanged and no duplicate content appears.
5. **`ingest_command_partial_failure`** — stub pipeline to fail on session 2 of 3; assert sessions 1 and 3 are reflected in wiki, session 2 is listed in error output, process exits non-zero.
6. **`ingest_command_contradiction_surfaced`** — stub pipeline to return a contradiction on one session; assert contradiction appears in summary output without the command failing.

### GREEN — implement minimally to pass each test

- Implement session-resolution logic that queries the P0-D state store for unprocessed sessions.
- Wire pipeline calls with per-session progress lines.
- Collect return values and render summary block.
- Pass the argument-parsing branch for targeted session IDs.

### REFACTOR

- Extract progress-reporter into a shared utility if other commands need incremental output.
- Ensure summary rendering is pure (testable without pipeline side effects).
- Confirm all tests pass after extraction; no behavior change.
