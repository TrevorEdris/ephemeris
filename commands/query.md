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
