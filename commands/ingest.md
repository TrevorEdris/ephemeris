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

`<staging_root>` is `$EPHEMERIS_STAGING_ROOT` if set and non-empty, else
`~/.claude/ephemeris/staging`.

Transcripts are captured by the hooks into one of two per-hook-type
subdirectories:

- `<staging_root>/session-end/<session-id>.jsonl` — written by the `SessionEnd` hook
- `<staging_root>/pre-compact/<session-id>.jsonl` — written by the `PreCompact` hook

After successful ingest each file is moved to a sibling `processed/` directory,
e.g. `<staging_root>/session-end/processed/<session-id>.jsonl`. A file is
considered **pending** when it lives directly in `<staging_root>/<hook-type>/`
and is **not** under any `processed/` subdirectory.

Run `Glob` twice to list the pending files (the single-`*` pattern is
non-recursive and therefore does not match files under `processed/`):

1. `Glob`: `<staging_root>/session-end/*.jsonl`
2. `Glob`: `<staging_root>/pre-compact/*.jsonl`

Union the two result lists. Remember each path's `<hook-type>` — it is the
parent directory name and is needed later for the `mv` target.

- If `$ARGUMENTS` is non-empty, filter to the session-id matching `$ARGUMENTS`
  (the filename stem). If zero matches, emit `No staged session matches <id>.`
  and stop.
- If the unioned list is empty, emit `No pending sessions to ingest.` and
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
   successfully written. Compute the processed path as
   `<staging_root>/<hook-type>/processed/<session-id>.jsonl`, then run:

   ```
   Bash: mkdir -p <staging_root>/<hook-type>/processed && mv <pending_path> <processed_path>
   ```

   The `mkdir -p` is idempotent. The `mv` rename is atomic on the same
   filesystem. `<hook-type>` is the parent directory name of `<pending_path>`
   (either `session-end` or `pre-compact`) recorded in step 2.

### 4. Error handling

- If any `Write` fails, stop processing the current session, do NOT run the
  `mv`, and continue to the next pending session. The JSONL stays in
  `<staging_root>/<hook-type>/` (outside any `processed/` subdirectory) and
  the next run retries it.
- If reasoning over a transcript produces zero extracted pages, still run the
  `mv` — the session was processed, it just had no wiki-worthy content. Emit
  `<session-id>: 0 pages (no extractable content)`.

### 5. Summary

After all sessions processed, emit one line per session:

`<session-id>: <N> pages created, <M> pages updated, <K> contradictions flagged`
