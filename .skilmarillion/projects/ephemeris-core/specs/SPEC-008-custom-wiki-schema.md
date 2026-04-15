# SPEC-008: Custom Wiki Schema

**Feature ID:** P2-B
**Size:** SMALL
**Risk:** MODERATE
**Status:** DRAFT
**Depends on:** P1-A (transcript capture), P1-B (ingestion pipeline)

## Problem Statement

The ephemeris ingestion pipeline uses a hardcoded default schema to instruct the ingestion AI on page types, naming conventions, and structural organization. Users working in specialized domains (e.g., cooking, project management, research) cannot align wiki output to their mental model without forking the plugin or modifying internal defaults. This feature allows users to provide a plain-text or markdown schema file at a well-known path; when present, it overrides the default schema injected into the ingestion prompt. When absent or malformed, the default applies automatically with no user-visible error.

## Acceptance Criteria

- **AC-1:** Given no schema file exists at `~/.claude/ephemeris/schema.md`, when ingestion runs, then the built-in default schema is used and ingestion completes without error or warning surfaced to the user.

- **AC-2:** Given a valid schema file exists at `~/.claude/ephemeris/schema.md`, when ingestion runs, then the user schema is injected into the ingestion prompt in place of the default schema.

- **AC-3:** Given a valid user schema is active, when the ingestion AI processes a transcript, then wiki pages are organized according to the page types and naming conventions defined in the user schema, not the default.

- **AC-4:** Given a schema file exists at `~/.claude/ephemeris/schema.md` but the file is empty, when ingestion runs, then the default schema is used and ingestion completes without error.

- **AC-5:** Given a schema file exists at `~/.claude/ephemeris/schema.md` but the file is syntactically or semantically malformed (e.g., binary content, encoding errors), when ingestion runs, then the default schema is used and a single warning is logged at debug level; no crash or user-facing error occurs.

- **AC-6:** Given an existing wiki built with the default schema, when a user adds a valid schema file and reruns ingestion, then no previously written wiki pages are deleted or overwritten with corrupt content; new and updated pages reflect the user schema.

- **AC-7:** Given an existing wiki built with a user schema, when the user removes the schema file and reruns ingestion, then no previously written wiki pages are deleted or overwritten with corrupt content; new and updated pages reflect the default schema.

- **AC-8:** Given a schema file exists at `~/.claude/ephemeris/schema.md`, when the file exceeds 64 KB in size, then the default schema is used and a single warning is logged at debug level indicating the file was skipped due to size.

- **AC-9:** Given the plugin is loading, when the schema loader is initialized, then it reads the schema file at most once per ingestion run and caches the result for that run; subsequent ingestion within the same run does not re-read disk.

## Architecture Recommendation

**Schema file location:** `~/.claude/ephemeris/schema.md`
- User-created, user-editable, not created or modified by the plugin.
- Plain text or markdown; no enforced syntax, intentionally permissive.

**Default schema:** Embedded as a string constant in the plugin source (e.g., `internal/schema/default.go` or equivalent). Not written to disk.

**Schema loader (`internal/schema/loader`):**
- `Load(path string) (string, error)` — reads file, validates (non-empty, readable, size <= 64 KB), returns content.
- `Resolve(path string) string` — calls `Load`; on any error or empty result, silently returns the embedded default; logs a debug-level warning on malformed/oversized input.
- Result is cached on the `Ingester` struct for the lifetime of a single ingestion run.

**Injection into ingestion prompt:**
- The ingestion prompt builder accepts a `schema string` parameter.
- Callers pass the result of `Resolve` unconditionally; the prompt builder has no knowledge of whether the schema is user-supplied or default.
- Schema is injected as a labeled block in the system prompt: `## Wiki Schema\n<schema content>`.

**Fallback strategy:**
- Empty file → default (silent).
- Malformed/unreadable → default + debug log.
- Oversized (> 64 KB) → default + debug log.
- File absent → default (silent).

**Schema switch safety:**
- Ingestion is append/upsert only; no ingestion path deletes existing pages.
- Schema affects only the AI's page-generation instructions, not any read or delete operations on existing wiki content.

## TDD Plan

**RED phase — write failing tests first:**

1. `TestSchemaLoader_FileAbsent` — `Resolve` returns default when path does not exist.
2. `TestSchemaLoader_ValidFile` — `Resolve` returns file content when file is valid.
3. `TestSchemaLoader_EmptyFile` — `Resolve` returns default when file is empty.
4. `TestSchemaLoader_MalformedFile` — `Resolve` returns default and logs debug warning when file contains binary/unreadable content.
5. `TestSchemaLoader_OversizedFile` — `Resolve` returns default and logs debug warning when file exceeds 64 KB.
6. `TestPromptBuilder_InjectsSchema` — prompt builder output contains the schema block with the correct content.
7. `TestIngester_UsesUserSchema` — end-to-end ingestion with a user schema file produces prompt containing user schema content.
8. `TestIngester_FallsBackToDefault` — end-to-end ingestion with absent schema file produces prompt containing default schema content.
9. `TestIngester_SchemaSwitchPreservesExistingPages` — wiki pages written during a default-schema run are present and unmodified after a subsequent user-schema ingestion run on the same wiki directory.
10. `TestIngester_ReverseSchemaSwitchPreservesExistingPages` — wiki pages written during a user-schema run are present and unmodified after a subsequent default-schema ingestion run.
11. `TestSchemaLoader_CachedPerRun` — `Resolve` called twice within a single ingestion run reads the file exactly once.

**GREEN phase:** Implement `SchemaLoader`, update prompt builder signature, wire `Resolve` into `Ingester`, add per-run cache.

**REFACTOR phase:** Extract schema injection into a named prompt section constant; ensure `Resolve` has no side effects beyond the debug log; confirm no ingestion code path holds a direct file reference past the loader.
