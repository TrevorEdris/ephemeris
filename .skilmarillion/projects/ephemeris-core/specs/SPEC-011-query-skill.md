# SPEC-011: Query Skill — Agent-Driven Body

**Feature ID:** P3-C
**Size:** SMALL
**Risk:** LOW (read-only; no wiki mutation path)
**Status:** DRAFT — awaiting approval
**Depends on:** SPEC-009 merged (stubs in place, wiki directory resolution documented)
**Parallel with:** SPEC-010 (ingest skill body) — no dependency between them.

## Problem Statement

SPEC-009 replaced `commands/query.md` with a stub that emits a "pending SPEC-011" message. The wiki is readable on disk, but there is no slash-command surface to ask questions against it. This SPEC replaces the stub body with full agent instructions the live Claude Code session follows to search wiki pages, ground answers in the read content, and cite sources — all using the session's own tool palette.

No writes, no mutations, no network. All reasoning happens in-session. Read-only skill.

## Non-Goals

- No wiki mutation. Not this SPEC, not any surface of this skill.
- No vector store, embedding index, or retrieval augmentation layer. Plain `Glob`/`Grep`/`Read` only.
- No ranking model beyond the match heuristic described in the contract.
- No pagination or multi-turn clarification — single question, single answer, single response.
- No schema change or wiki layout change.

## Acceptance Criteria

### Skill Body

- **AC-1:** `commands/query.md` frontmatter unchanged from SPEC-009 stub except `description` updated to: `Answer a question from the local wiki using the current session's model. Read-only.` `argument-hint` stays `"<question>"`. `allowed-tools` narrows to `[Read, Glob, Grep]` (no `Bash`, no `Write`).
- **AC-2:** Body replaces the SPEC-009 stub sentinel with ordered agent instructions matching the **Skill Contract** below. Zero occurrences of `python3 -m ephemeris.*` or any subprocess call to deleted Python modules.
- **AC-3:** Body explicitly instructs the session to resolve the wiki root via `$EPHEMERIS_WIKI_ROOT` (falling back to `~/.claude/ephemeris/wiki`).
- **AC-4:** Body explicitly instructs the session to `Glob` `<wiki_root>/**/*.md` to enumerate the wiki before searching.
- **AC-5:** Body explicitly instructs the session to `Grep` the question's key terms across the wiki (`output_mode: files_with_matches`), then `Read` the top matches (bounded: at most 5 files) in full.
- **AC-6:** Body explicitly instructs the session to answer **only from the content of the pages it actually `Read`**. It must not invoke training-data knowledge about the project.
- **AC-7:** Body explicitly instructs the session to emit a `## Sources` block at the end of the response listing every wiki page referenced in the answer, as relative paths under `<wiki_root>`.
- **AC-8:** Body contains a **grounding rule**: if the answer body mentions a claim that is not traceable to a listed source, the session must rewrite the answer to drop that claim or mark it with `(not found in wiki)`.
- **AC-9:** If `$ARGUMENTS` is empty, body instructs the session to emit `Usage: /ephemeris:query "<question>"` and stop.
- **AC-10:** If the wiki root exists but contains zero `.md` files, body instructs the session to emit `Wiki is empty — no pages have been built yet.` and stop.
- **AC-11:** If the wiki root does not exist, body instructs the session to emit `Wiki not found at <path>. Run /ephemeris:ingest first.` and stop.
- **AC-12:** If `Grep` returns zero matches for all derived key terms, body instructs the session to emit `Cannot answer this from the wiki — no relevant pages found.` followed by a (possibly empty) `## Sources` block and stop.

### Behavior

- **AC-13:** Running `/ephemeris:query "<question>"` on a populated wiki produces an answer whose `## Sources` block contains at least one real wiki path. Zero outbound network requests from the plugin.
- **AC-14:** Running `/ephemeris:query` with no arguments emits the usage sentinel.
- **AC-15:** Running `/ephemeris:query "something unrelated to any wiki content"` emits the cannot-answer sentinel — never a hallucinated answer.
- **AC-16:** Running `/ephemeris:query` against an empty/missing wiki emits the correct sentinel and does not error out.
- **AC-17:** The skill never calls `Write`, `Edit`, or `Bash`. The tool palette is the contract.

### Canary Eval (pre-merge manual gate)

- **AC-18:** Run the skill manually against 10 fixture (wiki, question) pairs drawn from populated canary wikis. For each:
  - If the wiki contains an answer, the skill produces it and cites the source.
  - If the wiki does not contain an answer, the skill emits the cannot-answer sentinel.
  - No answer contains a claim not present on a cited source page.
- **AC-19:** Document the canary eval results in the SPEC-011 PR description: 10/10 pass or a specific list of failures with root cause. Do not merge if <9/10 pass.

## Skill Contract

### `commands/query.md`

```markdown
---
description: Answer a question from the local wiki using the current session's model. Read-only.
argument-hint: "<question>"
allowed-tools:
  - Read
  - Glob
  - Grep
---

# /ephemeris:query

Answer a natural-language question about the user's project from the local
ephemeris wiki. All reasoning happens in this session — no subprocess, no API
key, no outbound calls. This skill is read-only: it never writes, edits, or
moves a file.

## Instructions

### 1. Parse the question

- If `$ARGUMENTS` is empty, emit `Usage: /ephemeris:query "<question>"` and
  stop.
- Otherwise, treat `$ARGUMENTS` as the question. Extract 3–6 key terms: nouns,
  named entities, distinctive verbs. Ignore stop-words and generic filler.

### 2. Resolve the wiki root

- `<wiki_root>` is `$EPHEMERIS_WIKI_ROOT` if set and non-empty, else
  `~/.claude/ephemeris/wiki`.
- If `<wiki_root>` does not exist, emit `Wiki not found at <path>. Run /ephemeris:ingest first.` and stop.

### 3. Enumerate the wiki

`Glob`: `<wiki_root>/**/*.md`.

- If zero results, emit `Wiki is empty — no pages have been built yet.` and
  stop.

### 4. Search for relevant pages

For each key term from step 1, run `Grep` with:
- `pattern`: the key term (case-insensitive)
- `path`: `<wiki_root>`
- `output_mode`: `files_with_matches`
- `glob`: `*.md`

Union the file paths returned across all terms. Rank by number of terms matched
(most terms = most relevant). Take the top 5.

- If the union is empty, emit `Cannot answer this from the wiki — no relevant pages found.` followed by an empty `## Sources` block and stop.

### 5. Read the top matches

For each of the top 5 files: `Read` the full file contents. Hold the content in
working memory.

### 6. Answer from read content only

Compose an answer to the question using **only** the content of the pages you
just `Read`. Do not draw on training-data knowledge about the project or
codebase — only what the wiki explicitly says.

**Grounding rule:** Every claim in the answer body must be traceable to a
specific wiki page you read. If the pages don't support a claim, drop the claim
or mark it `(not found in wiki)`. If none of the pages actually answer the
question, emit `Cannot answer this from the wiki — no relevant pages found.`
and skip to the `## Sources` block.

### 7. Cite sources

End the response with a `## Sources` block listing every wiki page referenced
in the answer, as relative paths under `<wiki_root>`. Example:

```
## Sources
- topics/authentication.md
- DECISIONS.md
- entities/AuthMiddleware.md
```

The `## Sources` block appears even when the answer is the cannot-answer
sentinel (possibly empty). It is the contract that tells the user what the
skill looked at.
```

## TDD Plan

SPEC-011 is a single-file rewrite (`commands/query.md`) whose body is prose instructions. There is no Python behavior to unit-test. Verification splits into two layers:

### RED — static guard tests

1. `tests/spec_011/test_query_skill_body.py`:
   - Parses `commands/query.md` frontmatter + body.
   - Asserts frontmatter has `description` matching the SPEC-011 string, `argument-hint: "<question>"`, `allowed-tools` exactly `[Read, Glob, Grep]` (no `Bash`, no `Write`, no `Edit`).
   - Asserts body contains each of: "Resolve the wiki root", "Glob", "Grep", "Read", "Sources", "Cannot answer", "Usage:", `$EPHEMERIS_WIKI_ROOT`.
   - Asserts body contains the SPEC-009 stub sentinel — **negated**.
   - Asserts body contains zero of: `python3 -m ephemeris`, `anthropic`, `ANTHROPIC_API_KEY`, `ephemeris.cli`, `Write`, `Edit`, `Bash`.
   - **Fails after SPEC-009 merges** (stub sentinel still present; allowed-tools mismatch).
2. `tests/spec_011/test_query_skill_grounding.py`:
   - Asserts body contains the grounding rule phrase (substring check: "only from the content" or "traceable to").
   - Asserts body contains the three sentinel strings: `Usage: /ephemeris:query`, `Wiki is empty`, `Cannot answer this from the wiki`.

### Canary eval — manual pre-merge gate (not automated)

Run the skill against 10 fixture (wiki, question) pairs. Record pass/fail per AC-18. PR description must include the eval results before merge. <9/10 pass = do not merge.

Fixture wikis live under `tests/fixtures/wikis/canary/<name>/` committed to the repo. Each fixture is a small hand-built wiki (5–15 pages) with a paired questions file (`questions.yaml`) listing question + expected-citation + should-answer-or-not.

### GREEN

- Replace `commands/query.md` body per Skill Contract.
- Commit fixture wikis + question files under `tests/fixtures/wikis/canary/`.
- Run canary eval manually; paste results into PR.

### REFACTOR

- Review body for clarity; ensure every step has a verb and a target.
- Ensure sentinel strings are copy-pastable (users will `grep` them).

### Verification gate

- `python -m pytest -q` passes (all static guard tests green).
- Canary eval ≥ 9/10.
- Manual smoke: `unset ANTHROPIC_API_KEY`, run `/ephemeris:query "what did we decide about authentication?"` against a populated canary wiki in a live Claude Code session, verify answer grounds in cited pages and `## Sources` block is non-empty.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Session hallucinates answers from training data instead of the wiki | Medium | High | Explicit grounding rule in step 6. Canary eval includes deliberately unanswerable questions to catch hallucination. |
| Grep term extraction too naive — misses synonyms and returns zero matches for valid questions | Medium | Medium | Canary eval includes paraphrased questions. Document limitation; defer synonym expansion to a future SPEC. |
| Top-5 cap excludes a relevant page | Low | Low | Sorting by term-match count puts the most relevant first. If a canary question fails due to cap, document it as a known limitation. |
| Session forgets the `## Sources` block | Low | Medium | Guard test asserts the string "Sources" appears in body. Canary eval checks the block is emitted. |
| Question contains shell metacharacters and breaks `$ARGUMENTS` expansion | Low | Low | Claude Code's argument passing handles this — no shell interpolation happens at the skill layer. Documented as non-issue. |
| User asks a question the wiki could answer if merged across pages, but no single page matches all terms | Medium | Low | The skill reads the top 5 matches in full — cross-page synthesis happens in-session. Canary eval includes multi-page questions. |

## Traceability

| PRD Requirement | How this SPEC satisfies it |
|---|---|
| FR-006 "Wiki Query via Slash Command" | AC-1..AC-12 — the skill IS the query command. |
| FR-006 AC "Answers cite the specific wiki pages used" | AC-7 + AC-8 — `## Sources` block + grounding rule. |
| FR-006 AC "Queries the wiki cannot answer are stated explicitly" | AC-10, AC-11, AC-12 — three distinct sentinel messages for empty wiki, missing wiki, and no-match. |
| NFR-001 "Zero external network requests" | AC-1..AC-17 — session-only reasoning, read-only tool palette. |
| NFR-004 "Failure Isolation" | Read-only skill; no mutation path exists. Cannot corrupt wiki. |
| Principle P-1 "In-Session, Not Alongside" | AC-2 + AC-17 — zero subprocess, narrowed tool palette. |

## Rollout

1. SPEC-009 merges first. `/ephemeris:query` becomes a stub.
2. SPEC-011 merges. First run of `/ephemeris:query` after merge returns real answers.
3. Users who ran `/ephemeris:query` between SPEC-009 and SPEC-011 merges saw the stub sentinel — harmless.
4. SPEC-010 and SPEC-011 can merge in either order; they have no runtime dependency on each other. Both depend on SPEC-009 landed.

## Open Questions

1. Should the skill read at most 5 top matches, or adapt to transcript budget? Default: hard cap at 5. A future SPEC can introduce adaptive sizing if canary eval shows the cap is hurting quality.
2. Should the `## Sources` block use absolute paths, paths relative to `<wiki_root>`, or paths relative to `~/.claude/ephemeris/wiki`? Default: relative to `<wiki_root>` — the user can always `cd` there. Revisit if canary users complain.
3. Should the skill dedupe against a recent-queries cache? No — slash commands are short-lived, cache adds complexity without measurable win. Out of scope.
