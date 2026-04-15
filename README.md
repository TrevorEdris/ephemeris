# ephemeris

> Silent session wiki for Claude Code. Captures every session automatically, distills it into a local markdown knowledge base, and lets you query it later.

Ephemeris is a Claude Code plugin that listens for session lifecycle events, stages the raw transcript, and incrementally builds a structured wiki of the decisions, entities, and topics that emerged from your work. Queries run against the wiki with citation-grounded answers — the model is explicitly forbidden from answering outside what the wiki contains.

ephemeris runs entirely inside your active Claude Code session. No API key. No outbound network. All model work is performed by the session's own tool palette.

Zero configuration for the default path. Opt-in scoping and schema customization for power users.

---

## How it works

```
Claude Code session
       │
       │  SessionEnd / PreCompact hook fires
       ▼
┌──────────────┐       ┌──────────────┐
│  bootstrap   │       │   capture    │
│  schema copy │       │  (hook py)   │
│              │       │              │
└──────────────┘       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │    stage     │
                       │  (JSONL +    │
                       │   journal)   │
                       └──────┬───────┘
                              │
                              │  /ephemeris:ingest (SPEC-010)
                              ▼
                       ┌──────────────┐
                       │     wiki     │
                       │  (markdown)  │
                       └──────┬───────┘
                              │
                              │  /ephemeris:query (SPEC-011)
                              ▼
                       ┌──────────────┐
                       │   grounded   │
                       │   answer +   │
                       │   citations  │
                       └──────────────┘
```

1. **Capture** — `hooks/post_session.py` and `hooks/pre_compact.py` run on Claude Code's `SessionEnd` and `PreCompact` events. Each hook bootstraps the default schema copy to `~/.claude/ephemeris/default-schema.md`, then reads the hook payload, validates the transcript path, and stages the raw JSONL to `~/.claude/ephemeris/staging/<hook_type>/<session_id>.jsonl` via atomic rename.
2. **Ingest** — the `/ephemeris:ingest` slash command (SPEC-010) walks the staging root, reads each transcript using the active session's own model, and applies the resulting page operations to `~/.claude/ephemeris/wiki/` through a transactional `StageWriter`.
3. **Query** — `/ephemeris:query "<question>"` (SPEC-011) runs retrieval over the wiki and returns an answer with an explicit `**Sources:**` block grounded entirely in captured content.

---

## Installation

Install via the Claude Code plugin marketplace:

```
/plugin marketplace add TrevorEdris/ephemeris
/plugin install ephemeris
```

That is the only required configuration. First hook fire creates the staging and wiki directories and bootstraps the default schema copy.

---

## Commands

| Command | Purpose |
|---|---|
| `/ephemeris:ingest` | Process every pending staged session (SPEC-010) |
| `/ephemeris:ingest <session-id>` | Process one specific session (SPEC-010) |
| `/ephemeris:query "<question>"` | Ask the wiki a question; returns grounded answer + citations (SPEC-011) |

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

The shipped default schema is copied to `~/.claude/ephemeris/default-schema.md` on every hook fire (idempotent, refreshed if a newer version ships).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `EPHEMERIS_STAGING_ROOT` | `~/.claude/ephemeris/staging` | Where hooks stage transcripts |
| `EPHEMERIS_WIKI_ROOT` | `~/.claude/ephemeris/wiki` | Where ingestion writes wiki pages |
| `EPHEMERIS_LOG_PATH` | `~/.claude/ephemeris/ephemeris.log` | Diagnostic log |
| `EPHEMERIS_SCOPE_CONFIG` | `~/.claude/plugins/ephemeris/scope.json` | Capture scope config path |

---

## Wiki layout

Pages are organized into three types:

```
<wiki_root>/
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

- **Stdlib-only.** No runtime dependencies. Standard library only.
- **In-session model execution.** All model work is performed by the Claude Code session using its own tool palette (`Read`, `Write`, `Bash`, `Glob`, `Grep`). No subprocess. No outbound network.
- **Atomic writes.** Every wiki page is written through `tempfile.mkstemp` + `os.replace` so readers never see partial content.
- **Transactional merges.** `StageWriter` writes a journal before touching any file. On crash, the next ingestion run scans for orphan journals and rolls back. Per-file rollback protects previously-existing pages from being left in a half-merged state.
- **Grounded queries only.** `/ephemeris:query` grounds the answer in captured wiki content. If the retrieved pages do not contain the answer, the model returns an explicit cannot-answer message.

---

## Development

```bash
git clone https://github.com/TrevorEdris/ephemeris
cd ephemeris
pip install -e ".[dev]"
python -m pytest -q
```

Test layout mirrors the spec layout: `tests/spec_00N/` contains all tests for SPEC-00N.

Run a single spec's tests:

```bash
python -m pytest tests/spec_009/ -v
```

---

## License

MIT — see [LICENSE](LICENSE).
