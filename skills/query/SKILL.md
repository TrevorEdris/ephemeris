---
name: query
description: Answer natural-language questions against the Graphiti knowledge graph. Use when the user asks about past decisions, problems, tech choices, or anything prefixed with "what did we decide / run into / pick for...". Surfaces typed entities with timestamps and optionally files the answer back as a new episode.
---

# /query

Thin wrapper around Graphiti's MCP search tools. The LLM does the synthesis; Graphiti does the retrieval. No Python script — every step runs in the LLM context with MCP calls.

## Prerequisites

- Graphiti MCP server running and configured (`docs/mcp-config.md`).
- At least one session ingested (otherwise every search returns empty).

## Algorithm

Given a question string `Q`:

1. **Search nodes**
   ```
   search_nodes(
     query=Q,
     group_ids=["workflow-knowledge", "codebase-history"],
     max_nodes=10,
   )
   ```
   Returns typed entity nodes — `Decision`, `Problem`, `TechChoice`, `JiraTicket`, `GitCommit`, etc.

2. **Search facts (edges)**
   ```
   search_memory_facts(
     query=Q,
     group_ids=["workflow-knowledge", "codebase-history"],
     max_facts=10,
   )
   ```
   Returns relationship edges — `Supersedes`, `CausedBy`, `Implements`, `PartOfEpic`, `Blocks`, `Duplicates` — with their `valid_at` / `invalid_at` timestamps.

3. **Merge** the two result sets. Nodes answer *what*; facts answer *how they relate and when*.

4. **Synthesize** a readable answer. Prefer the shape:
   - Lead with the direct answer (the `Decision.what` field, the `Problem.resolution`, etc.).
   - Cite the `Session` entity or `GitCommit` sha the entity came from.
   - Include temporal context when available: `"As of 2026-03-12, this was superseded by …"` — read `valid_at` / `invalid_at` off the edge.
   - If a `Supersedes` edge is present, always mention the newer decision alongside the old one.

5. **Offer to file the answer.** Ask: `"File this as a wiki page? (y/n)"`
   - If **yes**: run
     ```bash
     python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest/ingest_sessions.py \
       --episode-text "<synthesized answer>" \
       --name "<question>" \
       --group workflow-knowledge
     ```
     This uses the Python API (MCP `add_memory` cannot specify `entity_types`). The new episode compounds the graph — future `/query` calls will surface it.
   - If **no**: skip the ingest step silently.

## Why both `search_nodes` and `search_memory_facts`?

| Tool | Returns | Strength |
|---|---|---|
| `search_nodes` | Entity nodes with full `attributes` dict | Answers "what was decided / what broke" |
| `search_memory_facts` | Edges with `valid_at` / `invalid_at` | Answers "when and in what order; is this still current?" |

Using only one leaves blind spots — nodes without facts cannot surface supersession, and facts without nodes cannot show the actual decision rationale.

## Cost

One MCP round-trip per sub-call (two total), plus LLM synthesis. No local cost-control flags — if the question is expensive, rephrase or narrow `group_ids` to one group.

## Skill Behavior

1. Call `search_nodes` and `search_memory_facts` with the user's question verbatim.
2. Produce a structured answer in this order: **direct answer → source entity → temporal qualifier → related edges**.
3. If both calls return empty, say so and suggest `/ingest latest` — do not fabricate answers from model priors.
4. Ask the "file this as a wiki page?" question once. Only prompt again if the user explicitly requests more follow-ups.

## Example

> **User:** What did we decide about the graph backend?
>
> **Assistant:** (calls `search_nodes(query="graph backend decision")`)
> → Returns `Decision(what="Use Kuzu as default backend", why="Embedded, zero-server dev", alternatives="Neo4j, FalkorDB")` from session `2026-04-09_LLM-Wiki-Workflow`.
>
> (calls `search_memory_facts(query="graph backend decision")`)
> → Returns no Supersedes edge.
>
> **Answer:** We picked Kuzu for the graph backend because it's embedded and requires zero server setup (Neo4j and FalkorDB were the alternatives). Decided 2026-04-09 in the `LLM-Wiki-Workflow` session, and no later decision has superseded it.
>
> File this as a wiki page? (y/n)

## See Also

- [`../../docs/mcp-config.md`](../../docs/mcp-config.md) — Graphiti MCP server wiring
- [`../ingest/SKILL.md`](../ingest/SKILL.md) — the script `/query` calls when filing an answer
- [`../render/SKILL.md`](../render/SKILL.md) — browse the graph as markdown instead of querying it
