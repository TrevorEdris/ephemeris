# ephemeris

> Silent session wiki for Claude Code. Captures every session automatically, distills it into a local markdown knowledge base, and lets you query it later.

Ephemeris is a Claude Code plugin that listens for session lifecycle events, stages the raw transcript, and incrementally builds a structured wiki of the decisions, entities, and topics that emerged from your work. Queries run against the wiki with citation-grounded answers — the model is explicitly forbidden from answering outside what the wiki contains.

ephemeris runs entirely inside your active Claude Code session. No API key. No outbound network. All model work is performed by the session's own tool palette.

Zero configuration for the default path. Opt-in scoping and schema customization for power users.

---

## How it works (v0.4.0)

```
~/.claude/projects/<encoded-cwd>/<id>.jsonl   ← native Claude Code transcripts
                              │
                              │  /ephemeris:ingest
                              ▼
              ┌────────────────────────────┐
              │ Source readers             │
              │  - native-transcript       │
              │  - session-docs (opt-in)   │
              │  - arbitrary-md (paths)    │
              └─────────────┬──────────────┘
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

1. **Sources** — `/ephemeris:ingest` reads from one or more configured sources. The default config enables only `native-claude-projects`, which scans the JSONL transcripts Claude Code already writes to `~/.claude/projects/`. No staging copies, no hooks required. Power users can add `session-docs` or `arbitrary-md` sources via `~/.claude/ephemeris/config.json`.
2. **Cursor** — `~/.claude/ephemeris/cursor.json` records the last-seen mtime per locator so subsequent ingests are incremental.
3. **Citation dedup** — every wiki page has a `## Sessions` block; appending uses a stable `[YYYY-MM-DD <kind>:<id>]` key, so re-running ingest never duplicates citations.
4. **Query** — `/ephemeris:query "<question>"` runs retrieval over the wiki and returns an answer with an explicit `## Sources` block grounded entirely in captured content.

> **Migration from v0.1.x–v0.3.x:** the SessionEnd / PreCompact hooks are now no-ops. To replay backlog from prior installs run `python scripts/backfill.py --legacy-staging --with-cursor-init`.

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

### Multi-source config (`~/.claude/ephemeris/config.json`)

The default config is bootstrapped on first run. It enables only the universal native-transcript source:

```json
{
  "version": 1,
  "wiki_root": "~/.claude/ephemeris/wiki",
  "cursor_path": "~/.claude/ephemeris/cursor.json",
  "sources": [
    {
      "id": "native-claude-projects",
      "kind": "native-transcript",
      "root": "~/.claude/projects/",
      "scope": {
        "exclude": ["~/.claude/**", "**/ephemeris/**"]
      },
      "filter_title_gen": true
    }
  ]
}
```

Add a `session-docs` source to ingest your own dated session-doc tree:

```json
{
  "id": "my-session-docs",
  "kind": "session-docs",
  "root": "~/path/to/your/session-docs",
  "dir_pattern": "^(\\d{4}-\\d{2}-\\d{2})[_-](.+)$",
  "extractors": {
    "SESSION.md":   { "sections": ["Goal", "Decisions", "Status"] },
    "DISCOVERY.md": { "sections": ["Findings", "Gaps", "Open questions"] },
    "PLAN.md":      { "sections": ["Target files", "Steps", "Risks", "Verification"] }
  }
}
```

The plugin ships **no built-in heading patterns** — `extractors` is opt-in. With no patterns the source still works in pass-through mode (raw markdown handed to the model).

### Scope (cwd glob filtering for native-transcript)

The `scope` block on a `native-transcript` source filters by the JSONL's authoritative `cwd` field (with a fallback decode of the encoded directory name):

- `include`: list of glob patterns; if non-empty, only matching cwds are scanned.
- `exclude`: list of glob patterns; matching cwds are always skipped (wins over include).
- Glob syntax: `**` matches across path segments, `*` matches within one segment, `?` matches one non-slash char.

### Wiki schema override (optional)

Create `~/.claude/ephemeris/schema.md` to replace the built-in schema that instructs the ingestion model how to organize pages. Any plain-text or markdown content is accepted. Missing, empty, malformed, or oversized (> 64 KB) files silently fall back to the default schema.

The shipped default schema is copied to `~/.claude/ephemeris/default-schema.md` on every hook fire (idempotent, refreshed if a newer version ships).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `EPHEMERIS_WIKI_ROOT` | `~/.claude/ephemeris/wiki` | Where ingestion writes wiki pages |
| `EPHEMERIS_LOG_PATH` | `~/.claude/ephemeris/ephemeris.log` | Diagnostic log |
| `EPHEMERIS_SCHEMA_PATH` | (unset) | Override path to ingest schema |
| `EPHEMERIS_STAGING_ROOT` | `~/.claude/ephemeris/staging` | Legacy staging root (only used by `scripts/backfill.py --legacy-staging`) |

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

Every page ends with a `## Sessions` citation block listing contributing sessions in the format `> Source: [YYYY-MM-DD <kind>:<id-or-slug>]`. Citations are appended by the ingestion engine via `ephemeris.cli cite`, which dedups against both the new kind-prefixed format and the legacy `[YYYY-MM-DD <id>]` format used by v0.1.x–v0.3.x.

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
