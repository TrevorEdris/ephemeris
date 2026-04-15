# SPEC-003: Wiki Ingestion Engine

**Feature ID:** P0-C
**Size:** FEATURE
**Risk:** HIGH
**Status:** DRAFT
**Depends on:** P0-B (transcript capture)

## Problem Statement

Claude Code sessions produce transcripts that contain architectural decisions, naming conventions, discovered patterns, and component relationships — knowledge that currently evaporates when the session closes. The wiki ingestion engine reads a staged transcript, invokes the active Claude model to extract structured knowledge, and writes or updates markdown wiki pages so that information accumulates across sessions without any user action.

## Acceptance Criteria

*Organized as vertical slices — each independently shippable.*

### Slice 1: Schema Bootstrap

Delivers a default wiki schema embedded in the plugin and a schema document written to the wiki root on first run.

- AC-1.1: Given no wiki has been initialized, when the ingestion engine runs for the first time, then a schema document exists in the wiki directory describing page types, naming conventions, and cross-reference format.
- AC-1.2: Given a wiki already initialized, when ingestion runs again, then the existing schema document is not overwritten.
- AC-1.3: Given the schema document exists, when any wiki page is created, then its structure conforms to the conventions described in the schema (heading hierarchy, citation format, cross-reference syntax).
- AC-1.4: Given the schema is embedded in the plugin source, when no network is available, then schema bootstrap succeeds without any external calls.

### Slice 2: Single-Transcript Extraction

Delivers the core pipeline: one staged transcript in, one or more wiki page updates out.

- AC-2.1: Given a staged transcript, when ingestion completes, then the transcript is processed using only the active Claude model with no outbound HTTP calls to third-party services.
- AC-2.2: Given a staged transcript, when ingestion completes, then at least one wiki page has been created or updated with content sourced from that transcript.
- AC-2.3: Given a staged transcript, when ingestion completes, then each written page contains a citation identifying the source session date and session ID.
- AC-2.4: Given a staged transcript that contains no extractable knowledge (e.g., a session with only greetings), when ingestion completes, then no wiki pages are created and the transcript is still marked as processed.
- AC-2.5: Given a staged transcript, when the active model returns a malformed or empty response, then the engine logs the failure, does not write partial pages, and marks the transcript as failed rather than processed.
- AC-2.6: Given a staged transcript, when ingestion completes successfully, then the transcript file is removed from the staging directory (or marked consumed) so it is not reprocessed.

### Slice 3: Page Type Routing

Delivers distinct handling for topic pages, entity pages, and the decision log so extracted knowledge lands in the correct page type.

- AC-3.1: Given a transcript containing an architectural decision with stated rationale, when ingestion completes, then an entry appears in the decision log page including the decision, the rationale, and the session citation.
- AC-3.2: Given a transcript referencing a named component or system, when ingestion completes, then an entity page exists for that component containing its role and any relationships mentioned.
- AC-3.3: Given a transcript discussing a recurring pattern or convention, when ingestion completes, then a topic page exists capturing the pattern name, description, and usage context.
- AC-3.4: Given a page that already exists from a prior session, when new information about the same topic arrives, then the page is updated rather than replaced, and the prior content is preserved.
- AC-3.5: Given two pages that reference the same named entity, when ingestion completes, then each page contains a markdown link to the other.

### Slice 4: End-to-End Automation

Delivers zero-user-action ingestion triggered automatically after a session ends.

- AC-4.1: Given a session transcript captured by P0-B and placed in staging, when the session closes, then wiki pages are written without any explicit user command.
- AC-4.2: Given ingestion triggered automatically, when it completes, then the user can read populated wiki pages from the global wiki directory.
- AC-4.3: Given multiple transcripts queued in staging, when ingestion runs, then each transcript is processed independently and all produce wiki output.
- AC-4.4: Given an ingestion run that partially fails (some transcripts error), when the run completes, then successfully processed transcripts are marked consumed and failed transcripts remain in staging for retry.

## Architecture Recommendation

### Pipeline Stages

1. **Discover** — scan `~/.claude/ephemeris/staging/` for unprocessed transcript files.
2. **Schema load** — read the embedded default schema string; write `~/.claude/ephemeris/wiki/SCHEMA.md` if absent.
3. **Prompt construction** — for each transcript, build an ingestion prompt that embeds: (a) the full schema document, (b) the transcript text, (c) instructions to output a structured list of page operations (create/update, page type, page name, content).
4. **Model invocation** — call the active Claude model via the Claude Code plugin API (tool call or agent invocation). No `fetch`, no `axios`, no external endpoints.
5. **Response parsing** — parse the structured output from the model into discrete page operations.
6. **Page write** — for each page operation, merge new content into the existing page or create it. Append citations. Resolve cross-references by scanning the wiki index.
7. **Staging cleanup** — mark transcript consumed on success; leave in place with an error marker on failure.

### Default Wiki Schema

Three page types, each with a defined naming convention:

| Type | Directory | Naming | Required Sections |
|------|-----------|--------|-------------------|
| Topic | `wiki/topics/` | `kebab-case.md` | `## Overview`, `## Details`, `## Sessions` |
| Entity | `wiki/entities/` | `PascalCase.md` | `## Role`, `## Relationships`, `## Sessions` |
| Decision Log | `wiki/` | `DECISIONS.md` (single file) | `## [YYYY-MM-DD] <title>` entries with `**Decision:**`, `**Rationale:**`, `**Session:**` |

Cross-references use standard markdown links: `[ComponentName](../entities/ComponentName.md)`. Citations appear as `> Source: [YYYY-MM-DD session-id]`.

The schema document written to `wiki/SCHEMA.md` on first run contains this full specification so the model receives consistent instructions on every ingestion run.

### Page Merge Strategy

Pages are append-friendly. New `## Sessions` entries are appended. Decision log entries are prepended (newest first). Entity relationship sections are deduplicated by named reference. Topic `## Details` sections accumulate subsections tagged by session.

## TDD Plan

### Slice 1 — Schema Bootstrap

**RED**
- `schema_writes_on_first_run`: assert schema file does not exist, call bootstrap, assert file exists and contains required section headers.
- `schema_skips_existing`: write a sentinel schema file, call bootstrap, assert sentinel content is unchanged.
- `schema_content_valid`: call bootstrap, parse output, assert all three page types and their naming conventions are present.

**GREEN** — implement `bootstrapSchema(wikiDir)` that writes the embedded schema string only when the target file is absent.

**REFACTOR** — extract schema string to a separate constant; ensure bootstrap is idempotent under concurrent calls.

### Slice 2 — Single-Transcript Extraction

**RED**
- `processes_staged_transcript`: place a fixture transcript in a temp staging dir, run ingestion, assert at least one wiki page file exists.
- `no_external_calls`: mock the plugin model API; assert no `fetch` or HTTP client is called during ingestion.
- `citation_present`: run ingestion on a fixture transcript with known session metadata, assert output pages contain `> Source:` with session ID.
- `empty_transcript_no_pages`: run ingestion on a transcript with no substantive content, assert no wiki pages are written.
- `malformed_response_no_partial_write`: stub model to return empty string, assert no page files are written and transcript is marked failed.
- `transcript_consumed_on_success`: run ingestion, assert transcript no longer appears in staging as unprocessed.

**GREEN** — implement `ingestTranscript(transcript, wikiDir, modelClient)` covering happy path and the two failure modes.

**REFACTOR** — separate prompt construction from model invocation from page writing; each testable in isolation.

### Slice 3 — Page Type Routing

**RED**
- `decision_goes_to_decision_log`: fixture transcript contains explicit decision + rationale, assert `DECISIONS.md` entry created with both fields.
- `entity_page_created`: fixture transcript names a component, assert `entities/<ComponentName>.md` created with `## Role` section.
- `topic_page_created`: fixture transcript describes a pattern, assert `topics/<pattern-name>.md` created.
- `existing_page_preserved`: pre-populate an entity page, run ingestion with new info about same entity, assert original content present in updated page.
- `cross_references_linked`: fixture transcript mentions two named entities in relation, assert each entity page links to the other.

**GREEN** — implement page router that dispatches model output to the correct write strategy per page type.

**REFACTOR** — unify cross-reference resolution into a wiki index utility shared by all page types.

### Slice 4 — End-to-End Automation

**RED**
- `auto_trigger_after_session`: simulate session-end hook, assert ingestion runs without user command and wiki directory is non-empty.
- `multiple_transcripts_all_processed`: stage three fixture transcripts, run ingestion, assert all three are consumed and wiki has corresponding pages.
- `partial_failure_isolation`: stage two transcripts, stub model to fail on first and succeed on second, assert second produces pages and first remains in staging with error marker.
- `idempotent_on_rerun_of_success`: run ingestion twice on the same transcript (first run succeeds and marks consumed), assert second run does not duplicate pages.

**GREEN** — wire ingestion into the session-end hook; implement batch processor with per-transcript error isolation.

**REFACTOR** — extract retry eligibility check from staging scanner; ensure hook registration is a single call site.
