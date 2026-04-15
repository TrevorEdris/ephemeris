# ephemeris — Roadmap

## Current Status

**Phase:** 3 — Correction (implemented, pending merge)
**Last Updated:** 2026-04-15 (SPEC-009 + SPEC-010 + SPEC-011 implemented in single Phase 3 PR — 188 tests green)
**P0-B Completed:** 2026-04-15
**P0-C Completed:** 2026-04-15
**P0-D Completed:** 2026-04-15
**P1-A Completed:** 2026-04-15
**P1-B Completed:** 2026-04-15
**P2-A Completed:** 2026-04-15
**P2-B Completed:** 2026-04-15
**P3-A Completed:** 2026-04-15
**P3-B Completed:** 2026-04-15
**P3-C Completed:** 2026-04-15

### Completed
- [x] P0-A: Plugin Scaffolding + Hook Registration (feat/spec-001-plugin-scaffolding)
- [x] P0-B: Transcript Capture (feat/spec-002-transcript-capture)
- [x] P0-C: Wiki Ingestion Engine (feat/spec-003-wiki-ingestion-engine)
- [x] P0-D: Incremental Update + Contradiction Detection (feat/spec-004-incremental-update, PR #9 https://github.com/TrevorEdris/ephemeris/pull/9)
- [x] P1-A: Manual Ingest Trigger (feat/spec-005-manual-ingest-trigger, PR #10)
- [x] P1-B: Wiki Query (feat/spec-006-wiki-query, PR #11)
- [x] P2-A: Capture Scope Configuration (feat/spec-007-capture-scope-config, PR #12)
- [x] P2-B: Custom Wiki Schema (feat/spec-008-custom-wiki-schema, PR #13)
- [x] P3-A: Rip Subprocess + Bootstrap Default Schema + Stub Commands (SPEC-009, feat/phase-3-agent-driven)
- [x] P3-B: Ingest Skill Body (SPEC-010, feat/phase-3-agent-driven)
- [x] P3-C: Query Skill Body (SPEC-011, feat/phase-3-agent-driven)

### In Progress
*(none)*

### Pending
- [x] Phase 0: Silent Wiki — COMPLETE
- [x] Phase 1: Power-User Surface
- [x] Phase 2: Customization Layer
- [x] Phase 3: Correction — IMPLEMENTED

### Known Regressions

- **2026-04-15:** The Phase 0–2 implementation violates PRD principles P-1 (in-session execution), P-2 (zero-config), and P-3 (local-first / no network). `ephemeris/model.py` instantiates `anthropic.Anthropic()` and requires `ANTHROPIC_API_KEY`; `commands/ingest.md` and `commands/query.md` are subprocess wrappers instead of agent instructions. Phase 3 (SPEC-009) is the rip-and-replace correction. No deprecation path — MVP, rip-and-replace.

---

## Philosophy

Build the silent loop first and prove it. No visible surface until background ingestion is zero-config and bulletproof; every subsequent feature compounds on that foundation.

---

## Phase 0: Silent Wiki

**Entry Criteria:** Plugin repo exists at initial commit. Claude Code hook system confirmed available (post-session and pre-compaction hooks expose transcript content).

**Exit Criteria:** Installing the plugin and completing one session produces a populated global markdown wiki with no user configuration, commands, or input of any kind. A second session incrementally updates the wiki without duplication; contradictions are flagged.

### P0-A: Plugin Scaffolding + Hook Registration ✓ IMPLEMENTED

- **What:** Stand up the plugin structure so that Claude Code recognizes it on install and registers hook entry points. No ingestion logic yet — just wiring.
- **Depends on:** Nothing
- **Risk:** Claude Code hook API surface may differ from expectations; validate hook payload format early.
- **Checklist:**
  - [x] Define plugin manifest with skills, hooks, and agents directory structure
  - [x] Register pre-compaction hook entry point
  - [x] Register post-session hook entry point
  - [x] Verify plugin loads cleanly with zero user configuration on a fresh install
  - [x] Verify both hooks fire and their payloads are accessible (log payload shape for P0-B)

### P0-B: Transcript Capture ✓ IMPLEMENTED

- **What:** On each hook event, capture the session transcript and store it locally so the ingestion engine can process it. Nothing is written to the wiki yet.
- **Depends on:** P0-A
- **Risk:** Pre-compaction hook may not carry the same payload shape as post-session hook; handle both defensively.
- **Checklist:**
  - [x] Capture session transcript from pre-compaction hook payload
  - [x] Capture session transcript from post-session hook payload
  - [x] Store raw transcript to a consistent, predictable local path keyed by session
  - [x] Verify captured transcript is complete (not truncated) for a typical 60-minute session
  - [x] Verify capture is idempotent: re-running on the same session produces the same stored result

### P0-C: Wiki Ingestion Engine ✓ IMPLEMENTED

- **What:** Process a captured transcript through the active Claude model, extract key knowledge (decisions, patterns, conventions, rationale), and write it to the global markdown wiki. First run creates pages from scratch.
- **Depends on:** P0-B
- **Risk:** Largest scope item in Phase 0. Default wiki schema must be designed and embedded before this can produce useful output. Context window may be tight for very long sessions — chunk if needed.
- **Note:** Default wiki schema (page types, naming conventions, cross-reference format) is defined here as part of the ingestion prompt, not as a separate artifact.
- **Checklist:**
  - [x] Design default wiki schema: define page types (topic pages, entity pages, decision log), naming conventions, and cross-reference format
  - [x] Implement ingestion: process transcript → extract knowledge → write markdown wiki pages
  - [x] Write pages with consistent headings, cross-references, and source citations
  - [x] Store wiki in a single global directory accessible regardless of active project
  - [x] Verify wiki pages appear after a session ends with no user action
  - [x] Verify no external API calls are made during ingestion (active model only)

### P0-D: Incremental Update + Contradiction Detection

- **What:** Subsequent sessions update existing wiki pages rather than overwriting them. When new session content contradicts a prior claim, the contradiction is flagged visibly in the affected page.
- **Depends on:** P0-C
- **Risk:** Merge logic is the hardest part of the LLM Wiki pattern; new information must integrate without duplicating or silently overwriting prior knowledge.
- **Checklist:**
  - [x] Implement wiki page merge: new session information extends existing pages without duplication
  - [x] Implement contradiction detection: flag discrepancies between new and prior content in the relevant page
  - [x] Verify a second session updates pages rather than creating duplicates
  - [x] Verify contradictions are visible as flagged inline text in the affected page
  - [x] Verify a killed mid-run ingestion leaves prior wiki state intact (fault isolation)
  - [x] Verify a diagnostic log entry is produced on any ingestion failure

**Deliverable:** *Install the plugin, run one session, and a local markdown wiki exists. Run a second session and the wiki grows — no setup, no commands, no configuration required.*

---

## Phase 1: Power-User Surface

**Entry Criteria:** Phase 0 complete. Global wiki is being populated automatically. User can browse wiki markdown files.

**Exit Criteria:** Users can trigger ingestion on demand and ask the wiki natural language questions via slash commands.

### P1-A: Manual Ingest Trigger ✓ IMPLEMENTED

- **What:** A slash command lets the user force a wiki ingestion pass without waiting for the automatic post-session trigger.
- **Depends on:** P0-D
- **Risk:** Idempotency must be solid — double-ingesting a session must not corrupt the wiki.
- **Checklist:**
  - [x] Implement slash command that triggers an ingestion pass on pending or specified sessions
  - [x] Show in-progress feedback while ingestion runs
  - [x] Show completion summary (pages created, pages updated)
  - [x] Verify running the command twice on the same sessions produces no duplicate content

### P1-B: Wiki Query ✓ IMPLEMENTED

- **What:** A slash command accepts a natural language question and returns an answer synthesized from wiki content, with citations to the source pages used.
- **Depends on:** P0-D
- **Risk:** Query answers are only as good as the wiki content; poor ingestion quality will surface here. Explicit "I don't know" handling is required to prevent hallucination.
- **Checklist:**
  - [x] Implement slash command that accepts a natural language question
  - [x] Search wiki pages for relevant content
  - [x] Synthesize an answer with citations referencing the specific wiki pages used
  - [x] Respond explicitly and clearly when the wiki cannot answer the question
  - [x] Verify answers are drawn from wiki content, not from model training data alone

**Deliverable:** *Users can run a slash command to trigger ingestion on demand and ask the wiki questions like "what did we decide about authentication last week?" and receive cited answers.*

---

## Phase 2: Customization Layer

**Entry Criteria:** Phase 1 complete. Automatic ingestion and query are stable.

**Exit Criteria:** Users can configure what gets captured and optionally provide a custom schema that governs wiki structure.

### P2-A: Capture Scope Configuration ✓ IMPLEMENTED

- **What:** A configuration file lets users specify include/exclude rules for which projects, paths, or topics are captured during ingestion.
- **Depends on:** P1-A, P1-B
- **Risk:** Scope filtering that is too coarse will silently drop valuable context; needs clear documentation of what the rules match against.
- **Checklist:**
  - [x] Define configuration file format for include/exclude rules (JSON — see translation note)
  - [x] Apply scope rules during ingestion to filter session content
  - [x] Verify scope changes take effect on the next ingestion pass with no plugin restart
  - [x] Verify excluded content is not ingested into the wiki

### P2-B: Custom Wiki Schema ✓ IMPLEMENTED

- **What:** Users can provide a plain text or markdown schema file that overrides the default wiki structure, naming conventions, and page organization used during ingestion.
- **Depends on:** P1-A, P1-B
- **Risk:** A malformed user schema could break ingestion output quality; the default schema must always be a safe fallback.
- **Checklist:**
  - [x] Define schema file format (plain text or markdown, human-editable)
  - [x] Apply user schema during ingestion in place of the default schema when present
  - [x] Verify default schema applies cleanly when no user schema file exists
  - [x] Verify switching from default to user schema does not corrupt or delete existing wiki content

**Deliverable:** *Users who want control can configure exactly what gets captured and how the wiki is organized — without affecting the zero-config experience for users who don't.*

---

## Phase 3: Correction

**Entry Criteria:** Phases 0–2 shipped but violate PRD principles P-1, P-2, P-3 (see Known Regressions above).

**Exit Criteria:** The plugin runs entirely inside the active Claude Code session. No subprocess SDK pipeline, no `ANTHROPIC_API_KEY` requirement, no outbound HTTPS. Slash commands are agent instructions; helper CLIs exist only for operations the tool palette cannot guarantee (atomic writes, journal replay, traversal containment).

### P3-A: Rip Subprocess + Bootstrap Default Schema + Stub Commands — DRAFT (SPEC-009)

- **What:** Rip the subprocess model pipeline entirely. Delete `ephemeris/model.py`, `prompts.py`, `merge.py`, `ingest.py`, `query.py`, `wiki.py`, `schema.py`. Migrate `DEFAULT_SCHEMA` from a Python constant to a shipped `schema/default.md` file; add `bootstrap_default_schema()` to `ephemeris/capture.py` (atomic copy to `~/.claude/ephemeris/default-schema.md`, mtime-refresh, fail-soft) and wire it into both hooks. Replace `commands/ingest.md` and `commands/query.md` bodies with **stub sentinels** that point at SPEC-010 and SPEC-011 respectively — no ingest or query behavior lands in this SPEC. Keep only hook-side Python (`capture.py`, `stage.py`, `transcript.py`, `scope.py`, `log.py`, `exceptions.py`). Remove `anthropic` from `pyproject.toml`. Strip `ANTHROPIC_API_KEY` from `README.md`.
- **Depends on:** P2-B complete (all prior SPECs merged — this is a rewrite, not a dependency).
- **Risk:** HIGH. Large surface deletion, material test-suite shrinkage, queue grows while stubs are in place. Mitigated by TDD discipline (per SPEC-009 RED list), AST-based `test_no_anthropic_import` standing guard, and short runway between SPEC-009 and SPEC-010+011 merges.
- **Checklist:**
  - [ ] Create `schema/default.md` byte-equal to prior `DEFAULT_SCHEMA` constant
  - [ ] Add `bootstrap_default_schema()` to `ephemeris/capture.py` (atomic copy, mtime-refresh, fail-soft)
  - [ ] Wire `bootstrap_default_schema()` call into `hooks/post_session.py` and `hooks/pre_compact.py`
  - [ ] Delete `ephemeris/model.py`, `prompts.py`, `merge.py`, `ingest.py`, `query.py`, `wiki.py`, `schema.py`
  - [ ] Replace `commands/ingest.md` body with the SPEC-010 stub sentinel
  - [ ] Replace `commands/query.md` body with the SPEC-011 stub sentinel
  - [ ] Remove `anthropic` from `pyproject.toml`
  - [ ] Strip `ANTHROPIC_API_KEY` from `README.md` + update architecture diagram + document bootstrap behavior
  - [ ] Delete every test module that targets removed code
  - [ ] Add `tests/spec_009/**` guard suite (no-anthropic-import, commands-are-stubs, pyproject-no-anthropic, readme-no-api-key, default-schema-file-exists, no-deleted-symbol-references, schema-bootstrap)
  - [ ] Full suite green with `unset ANTHROPIC_API_KEY`

**Deliverable:** *Install the plugin on a machine with no `ANTHROPIC_API_KEY` set. Hooks still stage transcripts. Slash commands emit the stub sentinel pointing at the next SPEC. Zero subprocess model calls remain.*

### P3-B: Ingest Skill Body — DRAFT (SPEC-010)

- **What:** Replace the SPEC-009 stub body of `commands/ingest.md` with full agent instructions the live Claude Code session follows to drain `~/.claude/ephemeris/staging/pending/*.jsonl` into the wiki. Schema resolution chain (`$EPHEMERIS_SCHEMA_PATH` → `~/.claude/ephemeris/schema.md` → `<wiki_root>/SCHEMA.md` → bootstrapped `default-schema.md`). Merge-into-existing pages, contradiction flagging, `Bash: mv` to `processed/` on success. Error handling: on `Write` failure, JSONL stays in `pending/` for next-run retry. Pre-merge canary eval against 10 fixture staged sessions.
- **Depends on:** P3-A merged (stubs + infrastructure in place, bootstrap wired).
- **Parallel with:** P3-C. No runtime dependency between the two skills.
- **Risk:** MEDIUM. Runtime behavior change + ingestion quality risk. Mitigated by canary eval gate at ≥9/10.
- **Checklist:**
  - [ ] Replace `commands/ingest.md` body per SPEC-010 Skill Contract
  - [ ] Commit fixture JSONLs under `tests/fixtures/staging/canary/`
  - [ ] Add `tests/spec_010/**` static guard suite (body structure, keyword presence, negated stub sentinel)
  - [ ] Run canary eval manually; paste results into PR
  - [ ] Full suite green with `unset ANTHROPIC_API_KEY`
  - [ ] Canary eval ≥ 9/10

**Deliverable:** *`/ephemeris:ingest` drains the pending queue and writes wiki pages. Hooks stage, skill ingests, all in-session.*

### P3-C: Query Skill Body — DRAFT (SPEC-011)

- **What:** Replace the SPEC-009 stub body of `commands/query.md` with full agent instructions for a read-only query skill. Narrows `allowed-tools` to `[Read, Glob, Grep]` — no `Bash`, no `Write`. Body: parse question → resolve wiki root → `Glob` pages → `Grep` key terms → `Read` top 5 matches → answer **only** from read content → emit `## Sources` block. Explicit sentinels for empty wiki, missing wiki, no-match, and missing arguments. Grounding rule forbids claims not traceable to cited sources. Pre-merge canary eval against 10 fixture (wiki, question) pairs.
- **Depends on:** P3-A merged (stubs in place, wiki directory resolution documented).
- **Parallel with:** P3-B. No runtime dependency between the two skills.
- **Risk:** LOW. Read-only skill; no wiki mutation path; grounding rule enforced by canary eval.
- **Checklist:**
  - [ ] Replace `commands/query.md` body per SPEC-011 Skill Contract
  - [ ] Commit fixture wikis + `questions.yaml` under `tests/fixtures/wikis/canary/<name>/`
  - [ ] Add `tests/spec_011/**` static guard suite (body structure, allowed-tools narrowing, sentinel strings, grounding-rule phrase, negated stub sentinel)
  - [ ] Run canary eval manually; paste results into PR
  - [ ] Full suite green with `unset ANTHROPIC_API_KEY`
  - [ ] Canary eval ≥ 9/10

**Deliverable:** *`/ephemeris:query "<question>"` returns cited answers drawn only from wiki pages. Unanswerable questions return the cannot-answer sentinel instead of hallucinations.*

---

## Cross-Cutting Concerns

These constraints apply across all phases. Reference NFRs from the PRD.

| Concern | Requirement | NFR |
|---------|-------------|-----|
| No external API calls | All ingestion uses the active Claude model only. Zero network requests to external services. | NFR-001 |
| Ingestion latency | P90 < 60 seconds for a 60-minute session | NFR-002 |
| Storage growth | < 1 MB per 10 hours of coding | NFR-003 |
| Failure isolation | Any ingestion failure leaves prior wiki state intact; produces a diagnostic log entry | NFR-004 |
| No telemetry | Zero outbound connections initiated by the plugin outside the active Claude model | NFR-005 |

---

## Dependency Graph

```
P0-A (scaffolding)
  └── P0-B (transcript capture)
        └── P0-C (ingestion engine)
              └── P0-D (incremental update + contradiction detection)
                    ├── P1-A (manual ingest trigger)   ← parallel
                    └── P1-B (wiki query)               ← parallel
                          ├── P2-A (scope config)       ← parallel
                          └── P2-B (custom schema)      ← parallel
                                └── P3-A (rip + bootstrap + stub commands)
                                      ├── P3-B (ingest skill body)  ← parallel
                                      └── P3-C (query skill body)    ← parallel
```

**Critical path:** P0-A → P0-B → P0-C → P0-D → [P1-A or P1-B] → [P2-A or P2-B] → P3-A → [P3-B or P3-C]

---

## Dependency Summary

| Dependency | Source | Status |
|------------|--------|--------|
| Claude Code post-session hook (transcript payload) | Claude Code plugin system | Available — confirmed |
| Claude Code pre-compaction hook (transcript payload) | Claude Code plugin system | Available — confirmed |
| Active Claude model (for ingestion calls) | Claude Code session runtime | Available — no additional key required |
| Local filesystem write access (~/.claude/ or equivalent) | Host OS | Available |

---

## Spec Index

| ID | Name | Status | Phase | Roadmap Ref |
|----|------|--------|-------|-------------|
| SPEC-001 | Plugin Scaffolding + Hook Registration | IMPLEMENTED | 0 | P0-A |
| SPEC-002 | Transcript Capture | IMPLEMENTED | 0 | P0-B |
| SPEC-003 | Wiki Ingestion Engine | IMPLEMENTED | 0 | P0-C |
| SPEC-004 | Incremental Update + Contradiction Detection | IMPLEMENTED | 0 | P0-D |
| SPEC-005 | Manual Ingest Trigger | IMPLEMENTED | 1 | P1-A |
| SPEC-006 | Wiki Query | IMPLEMENTED | 1 | P1-B |
| SPEC-007 | Capture Scope Configuration | IMPLEMENTED | 2 | P2-A |
| SPEC-008 | Custom Wiki Schema | IMPLEMENTED | 2 | P2-B |
| SPEC-009 | Rip Subprocess + Bootstrap Default Schema + Stub Commands | DRAFT | 3 | P3-A |
| SPEC-010 | Ingest Skill — Agent-Driven Body | DRAFT | 3 | P3-B |
| SPEC-011 | Query Skill — Agent-Driven Body | DRAFT | 3 | P3-C |

---

- [ ] Generate all specs: `/fellowship:plan --specify ephemeris/.skilmarillion/projects/ephemeris-core/ROADMAP.md` → `.skilmarillion/projects/ephemeris-core/specs/SPEC-NNN-ephemeris-core.md`
