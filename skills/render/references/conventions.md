# Render Conventions

These conventions govern markdown output written by `/render` into `~/.ai/ephemeris/wiki/`. The source of truth is Graphiti, not the rendered markdown. Every rendered page must include enough metadata to be regenerated from the graph.

## Required Frontmatter

Every rendered page starts with:

```yaml
---
type: Decision          # or Problem, TechChoice, Session, JiraTicket, Epic, GitCommit
tags: [workflow-knowledge]   # the group_id at minimum; add topic tags as available
generated: 2026-04-10T14:23:00Z   # ISO-8601 UTC when the render was produced
graph_query: "search_nodes(query='<slug>', entity_types=['Decision'])"   # query to re-derive
source_uuid: "<graphiti node uuid>"
---
```

The `graph_query` field is used by `/lint` to detect render/graph divergence — the lint script re-runs each query and compares entity counts.

## "Generated View" Banner

Every rendered page must include this banner above the body:

```markdown
> This file is a generated view. The source of truth is Graphiti.
> Regenerate with `/render` or `python scripts/view/render.py`.
```

## File Layout

```
~/.ai/ephemeris/wiki/
├── index.md                 # catalog of all pages by type + date
├── log.md                   # render history (append-only timestamps + page counts)
├── Decision/
│   └── <slug>.md
├── Problem/
│   └── <slug>.md
├── TechChoice/
│   └── <slug>.md
└── ...
```

Slugs are derived from the entity's primary title field:
- `Decision.what` for decisions
- `Problem.symptom` for problems
- `TechChoice.technology` for tech choices
- `JiraTicket.key` for tickets
- `Epic.key` for epics
- `GitCommit.sha[:7]` for commits

## Templates

Templates live at `scripts/view/templates/*.j2`:

- `entity.md.j2` — renders a single entity page
- `index.md.j2` — renders `index.md`
- `log.md.j2` — renders `log.md` (append mode)

All text generation in default mode goes through Jinja2. No LLM calls.

## Narrated Mode (opt-in)

`/render --narrated` (or invoking the `/render` skill directly) uses an LLM to rewrite the templated output as prose. Higher quality, higher cost. Use when producing a polished view for human readers; skip otherwise.

## Never Do

- Do not edit rendered pages directly — changes will be overwritten on next render.
- Do not omit the `graph_query` frontmatter — `/lint` relies on it.
- Do not include the full episode body in a rendered page — link back via `source_uuid` instead.
