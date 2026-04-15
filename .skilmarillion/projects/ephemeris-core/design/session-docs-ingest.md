# Design: Markdown Session Docs Ingest

**Status:** proposed, not scheduled
**Created:** 2026-04-15
**Author:** TrevorEdris (via Claude Code)
**Supersedes:** n/a
**Related:** SPEC-010 (JSONL ingest skill)

## Context

Ephemeris currently ingests raw Claude Code session JSONL transcripts captured
by the `SessionEnd` and `PreCompact` hooks. A user's curated markdown session
documentation tree — `~/src/.ai/sessions/YYYY-MM-DD_<TICKET>_<SLUG>/` containing
`SESSION.md`, `DISCOVERY.md`, `PLAN.md` — is *not* ingested today.

The user wants this content surfaced in the wiki. Markdown session docs are
already distilled (decisions, problems, tech choices) whereas JSONL is raw, so
the same schema extraction should work and likely work *better* on the
markdown input.

This document captures the design options so we can revisit later. No
implementation is proposed yet.

## Goals

- Let the user populate the same ephemeris wiki (decisions / topics / entities)
  from their curated markdown session docs.
- Reuse the existing schema-driven extraction logic.
- Do not break or complicate the JSONL ingest pipeline.
- Idempotent: re-running over a session dir must not create duplicate pages or
  duplicate citations.

## Non-goals

- Automatically scanning `.ai/sessions/` on every Claude Code session start.
  (Option C below would add this; it is listed for completeness, not as a
  preferred direction.)
- Defining a new schema. The default schema's decisions / topics / entities
  categories apply to markdown just as well as JSONL.
- Replacing the JSONL ingest path. Both inputs co-exist.

## Input shape

A typical session dir looks like:

```
~/src/.ai/sessions/2026-04-15_TICKET-123_Auth-Refactor/
├── SESSION.md       # user prompts + summarized assistant responses, Q&A log
├── DISCOVERY.md     # technical analysis, gaps, data model notes
├── PLAN.md          # target files, ordered steps, risks, verification
└── (optional) NOTES.md, ERRATA.md, links/, screenshots/ …
```

The most valuable content for wiki extraction is `SESSION.md` + `DISCOVERY.md`
+ `PLAN.md`. Auxiliary files are optional and may or may not be worth reading
depending on the scope decision (see Open Questions).

## Options

### Option A — New skill `/ephemeris:ingest-docs <path>`

Add a second slash command that is exclusively responsible for markdown
session-dir ingest.

**Contract sketch:**

```yaml
---
description: Ingest a curated markdown session directory into the local wiki.
argument-hint: "<path-to-session-dir-or-parent>"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---
```

**Behavior:**

1. Resolve `<path>`. If it contains a `SESSION.md`, treat as a single session
   dir. Otherwise treat as a parent and `Glob <path>/*/SESSION.md` to discover
   session dirs.
2. For each session dir: `Read` `SESSION.md`, `DISCOVERY.md`, `PLAN.md` (each
   optional; skip absent files).
3. Reason over the concatenated markdown against the shipped schema (same one
   used by `/ephemeris:ingest`). Extract decisions / topics / entities.
4. Merge-write wiki pages using the same logic as SPEC-010 step 3c.
5. Emit a source citation derived from the dir name:
   `> Source: [YYYY-MM-DD session-dir-name]`
6. Record idempotency marker (see Open Questions).
7. Emit one-line summary per session dir.

**Pros:**
- Single responsibility per skill — `/ephemeris:ingest` stays a pure JSONL
  processor and its body doesn't grow branchy.
- Easy to test in isolation — fixture = a tmp session dir tree.
- Prompt wording for markdown-specific extraction can be tuned without risk
  to the JSONL path.
- Clear discoverability via `/plugin` or slash menu.

**Cons:**
- Two commands for users to remember.
- Two entry points to keep in sync if the schema format changes.

### Option B — Polymorphic `/ephemeris:ingest $ARGUMENTS`

Extend the existing command to accept a directory or file path and branch on
what it finds.

**Resolution rules:**
- `$ARGUMENTS` empty → process all pending JSONLs under `<staging_root>/`
  (today's behavior).
- `$ARGUMENTS` is a session-id string (no path separators, no `SESSION.md`
  under `<staging_root>/<hook-type>/<arg>/`) → filter staging JSONLs
  (today's behavior).
- `$ARGUMENTS` is a directory path (absolute or `~`-expanded) containing
  `SESSION.md` → reason over the markdown session dir (new).
- `$ARGUMENTS` is a directory path containing dated subdirs → iterate
  subdirs that contain `SESSION.md` (new).

**Pros:**
- Single command the user learns.
- Existing schema logic reused.

**Cons:**
- `/ephemeris:ingest` body becomes branchy; the skill contract needs a
  decision tree up front that is easy to misread.
- Test matrix grows: every error case has to be tested in both JSONL and
  markdown modes.
- Harder to surface "what will this run do?" in the argument hint — the
  hint becomes `"[<session-id> | <path>]"`.

### Option C — Capture-side bridge

Add a new hook or background step that scans `~/src/.ai/sessions/*/` on
Claude Code session start. Any new or modified session dir is copied (or
symlinked) into a dedicated staging area
`<staging_root>/session-docs/<dir-name>/` where the existing ingest skill
picks it up alongside JSONL files.

**Pros:**
- Fully automatic — the user never manually triggers ingest for markdown
  docs.
- Keeps a single manual trigger command if the user wants to also run
  on-demand.

**Cons:**
- Hooks are the part of ephemeris with the most failure modes. Adding a
  third hook action (file tree scan) increases the blast radius of every
  session start.
- Couples ephemeris to the `~/src/.ai/sessions/` convention defined in
  `CLAUDE.md`. Users without that convention get a dead code path.
- Requires change detection (mtime? content hash?) to avoid re-ingesting
  unchanged dirs every session start.
- The existing ingest skill would need to learn a third input type
  (markdown under `<staging_root>/session-docs/`) *in addition* to the
  JSONL types — effectively Option B plus a hook-side trigger.

## Recommendation

**Option A** — new `/ephemeris:ingest-docs` skill.

Rationale:
- Cleanest separation of concerns. Markdown reasoning and JSONL reasoning
  have different optimal prompts even if the schema output is the same.
- Smallest surface area to test.
- No risk to the JSONL path, which is the hot path for zero-config users.
- Users who don't keep markdown session docs simply don't invoke the
  command.
- Can be implemented as a single SPEC later without blocking anything
  else.

Option B is acceptable as a second choice if the user strongly prefers one
command. Option C should be rejected unless the user explicitly wants
automatic ingestion — the hook failure blast radius is too high for what
is effectively a convenience.

## Idempotency strategies (must decide before implementing)

1. **Sidecar file in session dir** — write `.ephemeris-ingested` containing
   an ISO timestamp and the wiki_root path on success. Re-run skips if
   sidecar is present and newer than all ingested `.md` files in the dir.
   - Pro: self-describing, co-located with the source.
   - Con: pollutes the user's session dir tree with ephemeris state.
2. **Central manifest** — `~/.claude/ephemeris/session-docs-processed.json`
   mapping session-dir path → ingest timestamp + source mtimes.
   - Pro: source dirs stay clean.
   - Con: manifest drift if the user moves or renames dirs.
3. **Mtime-only check** — no explicit marker; compare session-dir files'
   mtimes against the wiki page mtimes that cite them.
   - Pro: zero state.
   - Con: unreliable across filesystems, unsafe after editing a wiki page
     manually, and wiki pages cite *multiple* sources so mtime math is
     ambiguous.

Recommend **(1) sidecar file** for simplicity, with the caveat that the
user must approve adding ephemeris state to their session dir tree. Fall
back to (2) if the user objects.

## Open questions

1. Confirm Option A over B / C.
2. Idempotency marker: sidecar (recommended) vs central manifest vs
   mtime-only.
3. When invoked with a parent directory (e.g. `~/src/.ai/sessions/`),
   should the command sweep all subdirs or only unprocessed ones?
   Recommend: only unprocessed by default, add `--all` / explicit path to
   force reprocessing.
4. Scope: only `SESSION.md` + `DISCOVERY.md` + `PLAN.md`, or also any
   other `.md` the user has dropped in the dir? Recommend: canonical three
   by default; allow glob override.
5. Source citation format: `> Source: [YYYY-MM-DD session-dir-name]` is
   the SPEC-010 pattern for JSONL. For markdown docs the dir name already
   contains the date and slug — use the dir name verbatim as the citation
   label.
6. Should the command also ingest `INDEX.md` at `~/src/.ai/sessions/`
   root? That file is a generated cross-session index; ingesting it would
   create duplicate "this session was about X" topic pages. Recommend:
   explicitly exclude `INDEX.md`.
7. Interaction with `/ephemeris:query`: no change expected. Query reads
   wiki pages, regardless of which ingest skill wrote them. The `##
   Sources` block on each page will correctly cite mixed origins once both
   skills have run.

## Next step

Revisit this document after the user has test-run the JSONL ingest path
end-to-end. If the user confirms Option A and resolves the open questions,
write `SPEC-012-ingest-docs-skill.md` and implement behind a new
`fix/ingest-docs` branch following the same RED-GREEN discipline used for
SPEC-010.
