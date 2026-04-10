---
name: render
description: Render the Graphiti knowledge graph to browsable markdown under ~/.ai/ephemeris/wiki/. Use when the user wants a human-readable view of what's in the graph or when sharing the wiki outside Claude Code.
---

# /render

Generates markdown pages from a Graphiti group using Jinja2 templates. The rendered wiki is a **regeneratable view**, never the source of truth.

## Default (deterministic) mode — preferred

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/render.py
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/render.py --group codebase-history
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/render.py --wiki-root ~/custom/wiki
```

Zero LLM tokens. Templates in `scripts/view/templates/` (entity, index, log) handle all output formatting. See [`references/conventions.md`](references/conventions.md) for the output contract.

Output structure:

```
~/.ai/ephemeris/wiki/
├── index.md          # catalog by type + date
├── log.md            # append-only render history
├── Decision/
│   └── use-kuzu.md
├── Problem/
├── TechChoice/
└── ...
```

Every page includes:

- YAML frontmatter: `type`, `tags`, `generated`, `graph_query`, `source_uuid`
- A "generated view" banner above the body
- Fields from the entity's Pydantic type

## Narrated mode (opt-in, costs LLM tokens)

Invoke this skill directly (or pass `--narrated`) when you want the LLM to rewrite templated bullets as prose. Higher quality, higher cost. Use sparingly for polished human-readable output.

When this skill runs in narrated mode:

1. Call `fetch_entities(group_id)` via the Python API to get structured data.
2. For each entity, ask the LLM to rewrite the `fields` dict as a paragraph, preserving the frontmatter and "generated view" banner verbatim.
3. Write to `~/.ai/ephemeris/wiki/` the same way the templated mode does.
4. Append the render to `log.md` with a `mode: narrated` annotation.

## Skill Behavior

Default path (what this skill does most of the time):

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/render.py --group <group>` (default: `workflow-knowledge`).
2. Print the JSON result (`written`, `updated`, `total`).
3. Suggest running `/lint` next to check for stale pages.

Narrated path (only if `--narrated` is requested):

1. Warn the user that narrated mode costs LLM tokens.
2. Ask for confirmation unless the user already explicitly said "narrate".
3. Run the narrated pipeline.

## See Also

- [`references/conventions.md`](references/conventions.md) — rendered markdown contract
- [`docs/token-efficiency.md`](../../docs/token-efficiency.md) — why templated mode is default
