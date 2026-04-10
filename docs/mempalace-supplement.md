# MemPalace Supplement

ephemeris is a **synthesis layer** — it extracts typed entities (Decisions, Problems, TechChoices, Sessions, Commits, JiraTickets) into a temporal graph so `/query` can answer "what did we decide and when did it change". It is intentionally lossy: the LLM summarizes, entities replace prose, and old phrasings are dropped.

[MemPalace](https://github.com/milla-jovovich/mempalace) is a **retrieval substrate** — it stores raw conversation and artifact text verbatim in ChromaDB + SQLite and never asks an LLM to decide what is worth keeping. Lossless, verbatim, semantically searchable.

They solve different problems. Run them side by side if you need both *verbatim recall* and *structured reasoning*.

## When to Add MemPalace

Add it when any of the following matters:

- **Verbatim quotes** — you need the exact wording a customer or teammate used, not an LLM's paraphrase.
- **Regret-resistant archive** — you don't yet know what will be valuable six months from now, so you'd rather store everything than have an LLM prune it.
- **Conversation replay** — you want to re-read a past Claude/ChatGPT/Cursor session in its original form, not a graph projection of it.
- **Cross-tool recall** — you run Claude Code, Cursor, Gemini CLI, and ChatGPT, and need one shared memory that every tool can query.

Skip MemPalace if ephemeris alone (structured graph of decisions/problems/choices) already answers your questions. Most code-focused workflows do not need both.

## Setup

```bash
pip install mempalace
mempalace init
mempalace mine ~/src/.ai/sessions/ --mode convos
```

- `--mode convos` targets session docs (SESSION.md, DISCOVERY.md, PLAN.md).
- `--mode projects` targets code + READMEs + docs.
- `--mode general` auto-classifies into decisions, preferences, milestones, problems, emotional context.

ephemeris stores state under `~/.ai/ephemeris/`; MemPalace stores under its own directory (`~/.mempalace/` by default). They do not collide.

## Running Both MCP Servers Concurrently

Both exposes MCP servers. Add them to `~/.claude/settings.json` alongside each other — Claude Code loads all configured servers on startup.

```json
{
  "mcpServers": {
    "graphiti": {
      "command": "graphiti-mcp-server",
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "GRAPHITI_DB_PATH": "~/.ai/ephemeris/db"
      }
    },
    "mempalace": {
      "command": "mempalace-mcp-server"
    }
  }
}
```

After restart both tool surfaces are available:

| From | Tools |
|---|---|
| Graphiti (ephemeris) | `add_memory`, `search_nodes`, `search_memory_facts`, `get_episodes`, `get_status` |
| MemPalace | ~19 tools including `palace_search`, `wake_up`, `remember`, hall/wing/room CRUD |

Use `/query` to hit the graph, use MemPalace's tools to hit the verbatim corpus.

## Division of Labor (Recommended)

| Question | Tool |
|---|---|
| "What did we decide about backend X, and has that been superseded?" | ephemeris `/query` — typed Decisions + temporal edges |
| "What were the exact words the user used when they described the bug?" | MemPalace `palace_search` — verbatim recall |
| "Surface every Problem whose resolution was 'rolled back'" | ephemeris — structured graph filter |
| "Quote the PR description for the change that introduced auth middleware" | MemPalace — original PR body |
| "Browse past sessions as a wiki" | ephemeris `/render` (markdown view) |
| "Replay a Claude Code conversation from last Tuesday" | MemPalace session store |

## Known Issues (as of April 2026)

Per the MemPalace README and discovery notes captured in `.ai/sessions/2026-04-09_LLM-Wiki-Workflow/DISCOVERY.md`:

- **Shell injection in hooks (#110)** — do not wire MemPalace into Claude Code hooks that expand user-controlled variables into shell commands. Use the MCP server path only.
- **macOS ARM64 segfault (#74)** — intermittent crash during mining on Apple Silicon. Workaround: run `mempalace mine` under Rosetta (`arch -x86_64 mempalace mine ...`) or pin to the latest release that has the fix.
- **AAAK compression regression** — the 96.6% LongMemEval R@5 result is raw-mode only. With AAAK compression enabled, recall regresses to 84.2%. Run in raw mode unless storage pressure demands otherwise.
- **Fact checker not wired** — `fact_checker.py` exists but is not invoked by any user-facing command. Contradiction detection in MemPalace is effectively not active; rely on Graphiti's temporal invalidation instead.

## Why Not Replace ephemeris With MemPalace

They overlap at the edges but solve different problems:

- ephemeris has **custom Pydantic entity types** — Decisions, Problems, TechChoices extracted with a typed ontology. MemPalace does not extract typed entities; it stores raw text and filters on metadata.
- ephemeris has **temporal invalidation** — a Decision can be superseded and `/query` surfaces the replacement. MemPalace stores all facts forever.
- ephemeris renders a **browsable markdown wiki** (`/render`) with cross-links and per-type indices. MemPalace has wings/rooms/halls but they are navigation metaphors, not a rendered view.

If your workflow is "what did we decide, why, and is it still current?" — ephemeris is sufficient. If you also need "give me the exact transcript from last month's architecture meeting" — add MemPalace.

## See Also

- [`setup.md`](setup.md) — ephemeris setup
- [`mcp-config.md`](mcp-config.md) — MCP server wiring for Graphiti
- Upstream: https://github.com/milla-jovovich/mempalace
