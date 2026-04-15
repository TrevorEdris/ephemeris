# SPEC-004: Incremental Update + Contradiction Detection

**Feature ID:** P0-D
**Size:** FEATURE
**Risk:** HIGH
**Status:** IMPLEMENTED
**Depends on:** P0-C (wiki ingestion engine)

## Problem Statement

The initial ingestion engine (P0-C) creates wiki pages from session transcripts, but each subsequent ingestion run risks overwriting prior knowledge with a partial view of any given topic. The wiki must instead compound knowledge: new session content extends existing pages, duplicate facts are suppressed, and when new content directly contradicts a prior claim, the conflict is surfaced inline so the reader can evaluate it. Because ingestion runs in the background and may be interrupted, a failed mid-run must never leave the wiki in a partially-written or corrupted state.

## Acceptance Criteria

*Organized as vertical slices — each independently shippable.*

### Slice 1: Atomic Write Guarantee
A wiki write that is interrupted partway through leaves all previously-valid pages unchanged.

- AC-1.1: Given an in-progress ingestion that is killed (process terminated) after writing at least one page but before completing all pages, when the wiki is inspected afterward, then every page that existed before the run is byte-for-byte identical to its pre-run content.
- AC-1.2: Given an ingestion that fails due to an unexpected error during the write phase, when the wiki is inspected afterward, then no partially-written page exists (no page with truncated or malformed content).
- AC-1.3: Given any ingestion failure (interrupt or error), when the diagnostic log is inspected, then an entry exists recording the failure, the timestamp, and which session triggered the run.

### Slice 2: Merge Without Duplication
A second ingestion run on a new session extends existing wiki pages with net-new information and does not create duplicate pages or repeat facts already present.

- AC-2.1: Given a wiki page for topic T created by session A, when session B covers topic T with overlapping facts, then after ingestion the wiki contains exactly one page for topic T.
- AC-2.2: Given a wiki page for topic T with claim C already present, when session B repeats claim C verbatim or semantically, then the merged page does not contain duplicate instances of C.
- AC-2.3: Given a wiki page for topic T, when session B adds a genuinely new fact F about topic T not present in any prior page, then after ingestion the page for topic T includes F.
- AC-2.4: Given a session covering a topic T with no existing wiki page, when ingestion completes, then a new page for topic T is created as with the initial ingestion (no regression from P0-C behavior).

### Slice 3: Contradiction Detection and Inline Flagging
When new session content contradicts an existing wiki claim, the affected page displays a visible inline conflict marker.

- AC-3.1: Given a wiki page for topic T asserting claim C, when a new session asserts claim C' that directly contradicts C, then after ingestion the page for topic T contains a conflict block immediately adjacent to the relevant content.
- AC-3.2: Given a conflict block is present in a page, when the page is rendered, then the block begins with the marker `> ⚠️ Conflict:` followed by a description of the discrepancy and the session of origin for each conflicting claim.
- AC-3.3: Given a new session that does not contradict any existing claim, when ingestion completes, then no conflict block is added to any page.
- AC-3.4: Given a page with an existing conflict block for claim C, when a subsequent session resolves the contradiction by affirming one side, then the conflict block is replaced with the affirmed claim and no orphaned conflict marker remains.

### Slice 4: Diagnostic Log on Failure
Every ingestion failure produces a structured log entry sufficient to diagnose and replay the run.

- AC-4.1: Given an ingestion that fails at any phase (parse, merge, contradiction detection, write), when the log is inspected, then an entry exists with: ISO-8601 timestamp, session identifier, failure phase, and error message.
- AC-4.2: Given multiple successive ingestion failures, when the log is inspected, then each failure has a distinct log entry and prior entries are preserved (log is append-only).
- AC-4.3: Given a successful ingestion run, when the log is inspected, then a success entry exists with timestamp and session identifier (no silent no-ops).

## Architecture Recommendation

**Atomic write strategy:** Stage all page writes to a temporary directory (e.g., a sibling `ephemeris/.tmp-<run-id>/`) during the run. On success, atomically swap the staging directory into the live wiki using a rename (single syscall, OS-atomic on same filesystem). On any failure before the swap, delete the staging directory. This guarantees the live wiki is never in a partial state.

**Merge strategy:** On ingestion start, load all existing wiki pages into an in-memory index keyed by normalized topic slug. For each topic extracted from the new session, look up the existing page. If found, pass both the existing content and the new content to a merge prompt that: (a) deduplicates overlapping facts, (b) appends net-new facts, and (c) identifies contradictions. If not found, write a new page as in P0-C.

**Contradiction detection:** The merge prompt returns a structured result distinguishing three categories: `MERGE` (net-new additions), `DUPLICATE` (already present, discard), and `CONFLICT` (new claim contradicts existing). For each `CONFLICT` result, inject a conflict block into the merged page immediately following the existing claim. Conflict block format:

```
> ⚠️ Conflict: [Session <new-session-id>] asserts "<new claim>" which contradicts the prior claim above [from Session <prior-session-id>].
```

**Log format:** Append-only JSONL at `~/.claude/ephemeris/ephemeris.log`. Each line is a JSON object with fields: `ts` (ISO-8601), `session_id`, `phase` (`parse|merge|detect|write|complete`), `status` (`ok|error`), `message` (string, present on error).

**Staging directory cleanup:** A startup check clears any stale staging directories from prior aborted runs before beginning a new ingestion, preventing accumulation of orphaned temp state.

## TDD Plan

### Slice 1 — Atomic Write Guarantee (fault injection)

RED:
- Write a test that runs ingestion on a two-topic session, uses a hook to `SIGKILL` the process after the first page write, then asserts the pre-run wiki state is unchanged.
- Write a test that injects a panic/error during the write phase and asserts no partial files exist.
- Write a test that asserts a log entry is produced when the injected failure occurs.

GREEN:
- Implement staging-directory + atomic-rename write strategy.
- Implement failure cleanup (delete staging dir on error).
- Implement log append on failure.

REFACTOR:
- Extract staging lifecycle (create, populate, commit, rollback) into a single `StageWriter` abstraction with explicit `Commit()` and `Rollback()` methods.

### Slice 2 — Merge Without Duplication

RED:
- Write a test with an existing one-page wiki and a new session covering the same topic with overlapping and new facts; assert single page, no duplicated sentences, new fact present.
- Write a test where the new session covers an entirely new topic; assert existing pages unchanged, new page created.
- Write a test where the new session contains only duplicate facts; assert page is unchanged.

GREEN:
- Implement in-memory topic index loaded at ingestion start.
- Implement merge prompt call and result application.
- Wire merge output into the staging writer.

REFACTOR:
- Separate topic extraction, merge, and write into distinct pipeline stages with testable interfaces.

### Slice 3 — Contradiction Detection and Inline Flagging

RED:
- Write a test with a page asserting "X uses port 8080" and a session asserting "X uses port 9090"; assert the merged page contains `> ⚠️ Conflict:` adjacent to the port claim.
- Write a test with no contradiction; assert no conflict block appears anywhere.
- Write a test with an existing conflict block where the new session affirms one side; assert the block is replaced with the affirmed claim.

GREEN:
- Add `CONFLICT` category handling to merge prompt result parser.
- Implement conflict block injection into page content at the relevant location.
- Implement conflict resolution logic when an affirming session is detected.

REFACTOR:
- Extract conflict block rendering to a pure function testable independently of the ingestion pipeline.

### Slice 4 — Diagnostic Log on Failure

RED:
- Write a test that triggers a parse failure and reads the log; assert a JSONL entry with `phase: parse`, `status: error`, non-empty `message`, valid `ts`.
- Write a test that runs two consecutive failures; assert two distinct entries, first entry preserved.
- Write a test for a successful run; assert a `phase: complete`, `status: ok` entry.

GREEN:
- Implement append-only JSONL logger.
- Instrument all pipeline phases (parse, merge, detect, write, complete) with log calls.

REFACTOR:
- Inject the logger as a dependency so tests can use an in-memory logger without touching disk.
