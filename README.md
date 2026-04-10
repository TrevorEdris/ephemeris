# ephemeris

Ambient knowledge system for Claude Code — session artifacts, git history, and tickets flow into a temporal knowledge graph ([Graphiti](https://github.com/getzep/graphiti)). Query the graph with `/query`, render human-browsable markdown with `/render`, and lint for isolated or stale knowledge with `/lint`.

> An *ephemeris* is a table of time-indexed celestial positions. This plugin builds the same thing for your engineering work: decisions, problems, and tech choices indexed by when they happened and how they relate.

## What's Inside

| Component | What it does |
|---|---|
| `/ingest` | Feed a session directory (SESSION / DISCOVERY / PLAN) into Graphiti |
| `/render` | Generate browsable markdown from the graph (Jinja2 templates; no LLM by default) |
| `/query` | Natural-language search over the graph, with optional "file this answer" |
| `/lint` | Deterministic health checks: isolated nodes, stale renders, render/graph divergence |
| `hooks/session-reminder.js` | Nudges you to create a session directory (inherited from FOTW) |
| `hooks/workflow_phase_reminder.py` | Brief phase-specific reminder on each prompt |
| `hooks/session_ingest.py` | Auto-ingest of the previous session at the start of a new one |
| `hooks/context-snapshot.js` | Pre-compact context snapshot (inherited from FOTW) |

## Install

Clone and install as a Claude Code plugin:

```bash
gh repo clone TrevorEdris/ephemeris ~/src/github.com/TrevorEdris/ephemeris
claude plugin install ~/src/github.com/TrevorEdris/ephemeris
```

Install Python dependencies:

```bash
cd ~/src/github.com/TrevorEdris/ephemeris
pip install -e ".[dev]"
```

Configure an LLM provider (required — every `add_episode()` call runs LLM inference):

```bash
# Default: OpenAI
export OPENAI_API_KEY=sk-...

# Or Anthropic — pass AnthropicClient() at Graphiti() init; see docs/setup.md
export ANTHROPIC_API_KEY=sk-ant-...
```

See [docs/setup.md](docs/setup.md) for Kuzu / Neo4j / FalkorDB backing store options and [docs/mcp-config.md](docs/mcp-config.md) for MCP wiring.

## Quick Start

```bash
# 1. Ingest a completed session into the graph
/ingest latest

# 2. Query the graph
/query "what did we decide about authentication?"

# 3. Render a browsable view
/render

# 4. Check graph health
/lint
```

## Architecture

```
Session artifacts ──┐
Git log + PRs ──────┼─► Graphiti (Kuzu / Neo4j) ─► /query, /render, /lint
Jira tickets ───────┘                            │
                                                 └─► ~/.ai/ephemeris/wiki/  (markdown view)
```

- **Graphiti** is the source of truth — a temporal knowledge graph with LLM-powered entity extraction, hybrid retrieval (semantic + BM25 + graph traversal), and automatic contradiction handling via temporal validity windows.
- **Rendered markdown** in `~/.ai/ephemeris/wiki/` is a regeneratable view, not the source of truth.
- **LSP and Graphiti are complementary**: LSP answers "where/what/how" in current code; Graphiti answers "why does this exist and what changed it" via architectural history.

## Non-Claude Usage

The Python scripts and the Graphiti MCP server are tool-agnostic:

- **Cursor, Windsurf, any MCP-supporting tool** — the Graphiti MCP server works everywhere. Python CLI tools run from any terminal.
- **Skills, hooks, and agents** are Claude Code specific. Porting to other tools would require rewriting each in the target format.

## Scripting Policy

All new executable logic is Python 3, stdlib-first. See [docs/token-efficiency.md](docs/token-efficiency.md) for rationale. Inherited FOTW hooks (`session-reminder.js`, `context-snapshot.js`) remain Node JavaScript.

## Testing

```bash
pytest                       # full suite
pytest tests/hooks -v        # hook tests only
```

## Extracted from FOTW

Two skills are copied verbatim from [fellowship-of-the-workflows](https://github.com/TrevorEdris/fellowship-of-the-workflows):

- `skills/session-handoff/` — handoff documents for session continuity
- `skills/session-index/` — cross-session index maintenance

Three FOTW rules were converted to ephemeris-native forms because plugins cannot distribute rules:

- `ai-session` → `skills/session-handoff/references/session-conventions.md`
- `discover-plan-implement` → `docs/workflow-phases.md` + `hooks/workflow_phase_reminder.py`
- `context-efficiency` → `docs/token-efficiency.md`

## License

See [LICENSE](LICENSE).
