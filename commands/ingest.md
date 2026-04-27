---
description: Ingest Claude Code session content into the local wiki using the current session's model.
argument-hint: "[<path-or-flags>]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
---

# /ephemeris:ingest

Process Claude Code session content into the local wiki. All model reasoning
happens in this session — no subprocess, no API key, no outbound calls.

The command reads from one or more **sources**. By default the only enabled
source is `native-claude-projects`, which scans the JSONL transcripts Claude
Code already writes to `~/.claude/projects/`. No staging, no duplication, no
hooks required.

## Invocation forms

- `/ephemeris:ingest` — walk every source declared in
  `~/.claude/ephemeris/config.json` (a sensible default is bootstrapped on
  first run); ingest only locators newer than the cursor watermark.
- `/ephemeris:ingest <path>` — ingest one path explicitly. Auto-detected:
  - A `*.jsonl` file → treat as a native transcript.
  - A directory under `~/.claude/projects/` → scan as native-transcript root.
  - A directory matching `<config>.dir_pattern` (or any directory containing
    `*.md` files when no pattern is configured) → scan as a session-docs
    root, or read as a single session-docs locator if the path itself is a
    leaf session directory.
  - A single `*.md` file → arbitrary-markdown source.
- `/ephemeris:ingest --since=<iso-date>` — restrict to locators with mtime ≥
  the given date.
- `/ephemeris:ingest --session=<id>` — ingest only the locator whose
  identifier equals `<id>`.
- `/ephemeris:ingest --dry-run` — list what would be ingested; no writes.
- `/ephemeris:ingest --legacy-staging` — also walk
  `~/.claude/ephemeris/staging/{session-end,pre-compact,processed,pending}/*.jsonl`
  to mop up content captured by the pre-v0.2 hook pipeline. Idempotent;
  citation dedup makes re-runs safe.

## Instructions

### 1. Resolve the schema

Try each of these in order; use the first that exists and is non-empty.
Hold the schema text in working memory for this run only.

1. `$EPHEMERIS_SCHEMA_PATH` — `Bash: echo "$EPHEMERIS_SCHEMA_PATH"`; if
   non-empty, `Read` that path.
2. `~/.claude/ephemeris/schema.md` — user personal override.
3. `<wiki_root>/SCHEMA.md` where `<wiki_root>` is the resolved wiki root
   (env `$EPHEMERIS_WIKI_ROOT` or config's `wiki_root`, defaulting to
   `~/.claude/ephemeris/wiki`).
4. `~/.claude/ephemeris/default-schema.md` — shipped default.

### 2. Resolve sources

`Bash: /usr/bin/env python3 -m ephemeris.cli list-sources --config <path>`
prints one line per resolved source:

    <source-id>\t<kind>\t<root>

When `$ARGUMENTS` is a single path, ignore the config and treat the path
according to the auto-detection rules in "Invocation forms" above. When
`$ARGUMENTS` is empty, walk every source.

### 3. Enumerate locators

For each resolved source, run:

    /usr/bin/env python3 -m ephemeris.cli scan --source <source-id>

This returns one line per pending locator (filtered by cursor watermark
unless `--ignore-cursor` is passed):

    <kind>\t<identifier>\t<when>\t<absolute-path>

If `--session=<id>` was supplied, filter to matching identifier. If
`--since=<iso>` was supplied, drop locators with `when` earlier than the ISO
date.

If the union is empty, emit `No pending content to ingest.` and stop.

### 4. Process each locator

For each locator:

a. `Bash: /usr/bin/env python3 -m ephemeris.cli read --source <source-id>
   --identifier <identifier>` returns a JSON document with
   `{raw_text, structured_sections, metadata}`. Read it.

b. Reason over `raw_text` (and any `structured_sections` block) against the
   schema. Extract decisions, entities, and topics per the schema's contract.

c. For each extracted page:
   - Compute the canonical filename per the schema (`DECISIONS.md`,
     `topics/<kebab>.md`, `entities/<Pascal>.md`).
   - `Glob` `<wiki_root>/**/<canonical-name>` to check existence.
   - **If exists:** `Read`, merge new content into the appropriate section,
     `Write` back.
   - **If new:** build content from the schema's page template; `Write`.
   - Append a citation via:
     `Bash: /usr/bin/env python3 -m ephemeris.cli cite --page <path>
     --when <YYYY-MM-DD> --kind <source-kind> --identifier <id>`. The CLI
     dedups: if a citation for `(when, kind, id)` already exists on the
     page, no change is made.

d. Mark the locator consumed in the cursor:
   `Bash: /usr/bin/env python3 -m ephemeris.cli mark --source <source-id>
   --identifier <id> --mtime <epoch>`.

### 5. Error handling

- Page-write failure on a locator → skip cursor `mark`; the next run will
  retry. Continue to the next locator.
- Reasoning produces zero pages → still call `mark` (the locator was
  processed; it just had no wiki-worthy content). Emit
  `<id>: 0 pages (no extractable content)`.

### 6. Summary

After every locator is handled, emit one line per locator:

    <id>: <N> pages created, <M> pages updated, <K> contradictions flagged

End with a totals line.
