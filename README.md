# ephemeris

> Silent session wiki for Claude Code. Captures every session automatically, distills it into a local markdown knowledge base, and lets you query it later.

Ephemeris is a Claude Code plugin that listens for session lifecycle events, stages the raw transcript, and incrementally builds a structured wiki of the decisions, entities, and topics that emerged from your work. Queries run against the wiki with citation-grounded answers — the model is explicitly forbidden from answering outside what the wiki contains.

Zero configuration for the default path. Opt-in scoping, schema customization, and an override env for power users.

---

## How it works

```
Claude Code session
       │
       │  SessionEnd / PreCompact hook fires
       ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   capture    │──────▶│    stage     │──────▶│    ingest    │
│  (hook py)   │       │  (JSONL +    │       │  (model +    │
│              │       │   journal)   │       │   merge)     │
└──────────────┘       └──────────────┘       └──────┬───────┘
                                                     │
                                                     ▼
                                            ┌──────────────┐
                                            │     wiki     │
                                            │  (markdown)  │
                                            └──────┬───────┘
                                                   │
                                                   │  /ephemeris:query
                                                   ▼
                                            ┌──────────────┐
                                            │   grounded   │
                                            │   answer +   │
                                            │   citations  │
                                            └──────────────┘
```

1. **Capture** — `hooks/post_session.py` and `hooks/pre_compact.py` run on Claude Code's `SessionEnd` and `PreCompact` events. Each reads the hook payload, validates the transcript path, and stages the raw JSONL to `~/.claude/ephemeris/staging/<hook_type>/<session_id>.jsonl` via atomic rename.
2. **Ingest** — the `/ephemeris:ingest` slash command (or the `python -m ephemeris.ingest` CLI) walks the staging root, parses each transcript, calls an LLM with the configured wiki schema, and applies the resulting page operations to `~/.claude/ephemeris/wiki/` through a transactional `StageWriter`. Journals are written before any file mutation, so crashes recover on the next run.
3. **Query** — `/ephemeris:query "<question>"` runs a token-overlap retrieval over the wiki, assembles a grounded system prompt, and returns an answer with an explicit `**Sources:**` block. If no page is relevant, it returns an explicit "cannot answer" message instead of hallucinating.

---

## Installation

Install via the Claude Code plugin marketplace:

```
/plugin marketplace add TrevorEdris/ephemeris
/plugin install ephemeris
```

Set your API key once:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

That is the only required configuration. First hook fire creates the staging and wiki directories.

---

## Commands

| Command | Purpose |
|---|---|
| `/ephemeris:ingest` | Process every pending staged session |
| `/ephemeris:ingest <session-id>` | Process one specific session |
| `/ephemeris:query "<question>"` | Ask the wiki a question; returns grounded answer + citations |

Both commands also run as Python modules:

```bash
python3 -m ephemeris.ingest            # all pending
python3 -m ephemeris.ingest <sid>      # one session
python3 -m ephemeris.ingest --dry-run  # plan without writing
python3 -m ephemeris.query "What did we decide about error handling?"
```

---

## Configuration

Ephemeris reads from well-known paths under `~/.claude/ephemeris/` and honors a small set of environment overrides.

### Capture scope (optional)

Create `~/.claude/plugins/ephemeris/scope.json` to filter which sessions get captured by cwd:

```json
{
  "include": ["/Users/me/src/work/**"],
  "exclude": ["/Users/me/src/work/secrets/**"]
}
```

- Glob syntax: `**` matches across path segments, `*` matches within one segment, `?` matches one non-slash char.
- Exclude wins over include. Sessions whose cwd matches any exclude pattern are always skipped.
- If the file is absent, all sessions are captured (default is permissive).
- If the file is present but invalid JSON, a warning is logged and capture falls back to permissive.
- Config re-reads on every hook invocation — no restart needed.

### Wiki schema override (optional)

Create `~/.claude/ephemeris/schema.md` to replace the built-in schema that instructs the ingestion model how to organize pages. Any plain-text or markdown content is accepted. Missing, empty, malformed, or oversized (> 64 KB) files silently fall back to the default schema.

Precedence when resolving schema:

1. `EPHEMERIS_SCHEMA_PATH` env var (if set and valid)
2. `~/.claude/ephemeris/schema.md` (if present and valid)
3. `<wiki_root>/SCHEMA.md` (per-wiki override, bootstrapped on first ingest)
4. Built-in `DEFAULT_SCHEMA` constant

The file is read at most once per ingestion run.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | _required_ | Anthropic API key for ingest + query model calls |
| `EPHEMERIS_STAGING_ROOT` | `~/.claude/ephemeris/staging` | Where hooks stage transcripts |
| `EPHEMERIS_WIKI_ROOT` | `~/.claude/ephemeris/wiki` | Where ingestion writes wiki pages |
| `EPHEMERIS_LOG_PATH` | `~/.claude/ephemeris/ephemeris.log` | Diagnostic log |
| `EPHEMERIS_MODEL_CLIENT` | `anthropic` | `anthropic` or `fake` (for testing) |
| `EPHEMERIS_SCOPE_CONFIG` | `~/.claude/plugins/ephemeris/scope.json` | Capture scope config path |
| `EPHEMERIS_SCHEMA_PATH` | _unset_ | Absolute path to a schema file that overrides all other sources |

---

## Wiki layout

Pages are organized into three types:

```
<wiki_root>/
├── SCHEMA.md              # bootstrapped default schema (editable)
├── DECISIONS.md           # newest-first decision log
├── topics/
│   ├── error-handling-strategy.md
│   └── api-design-patterns.md
└── entities/
    ├── TranscriptCapture.md
    └── IngestEngine.md
```

| Type | Directory | Naming | Required sections |
|---|---|---|---|
| Topic | `topics/` | `kebab-case.md` | Overview, Details, Sessions |
| Entity | `entities/` | `PascalCase.md` | Role, Relationships, Sessions |
| Decision | `DECISIONS.md` | `## [YYYY-MM-DD] <title>` | Decision, Rationale, Session |

Every page ends with a `## Sessions` citation block listing contributing sessions in the format `> Source: [YYYY-MM-DD session-id]`. Citations are appended by the ingestion engine — the model never writes them itself.

---

## Design invariants

- **Stdlib-first.** The only runtime dependency is `anthropic`. No YAML, no BM25 library, no click — standard library only for everything else.
- **Atomic writes.** Every wiki page is written through `tempfile.mkstemp` + `os.replace` so readers never see partial content.
- **Transactional merges.** `StageWriter` writes a journal before touching any file. On crash, the next ingestion run scans for orphan journals and rolls back. Per-file rollback protects previously-existing pages from being left in a half-merged state.
- **Grounded queries only.** `/ephemeris:query` injects a grounding instruction into the system prompt. If the retrieved pages do not contain the answer, the model is instructed to return `Cannot answer this from the wiki — no relevant pages found.` rather than drawing on training knowledge.
- **Token-overlap retrieval.** No vector store, no embedding model. Pages are ranked by lowercase word-set intersection with the query. Simple, deterministic, fast.

---

## Development

```bash
git clone https://github.com/TrevorEdris/ephemeris
cd ephemeris
pip install -e ".[dev]"
python -m pytest -q
```

Test layout mirrors the spec layout: `tests/spec_00N/` contains all tests for SPEC-00N. The fake model client in `ephemeris.model.FakeModelClient` is used by every integration test — the `AnthropicModelClient` is only exercised by explicitly-gated tests that stub the network boundary.

Run a single spec's tests:

```bash
python -m pytest tests/spec_006/ -v
```

---

## License

MIT — see [LICENSE](LICENSE).
