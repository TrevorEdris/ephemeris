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
