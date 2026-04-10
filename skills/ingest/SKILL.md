---
name: ingest
description: Ingest a completed session directory into the Graphiti knowledge graph. Use when the user finishes a session, says "ingest this", or references prior sessions that may not yet be in the graph.
---

# /ingest

Feeds a session directory under `~/src/.ai/sessions/` into Graphiti's `workflow-knowledge` group, extracting `Decision`, `Problem`, `TechChoice`, and `Session` entities.

## Prerequisites

- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` set in the environment.
- `graphiti-core[kuzu]` installed (`pip install -e "${CLAUDE_PLUGIN_ROOT}[dev]"`).
- The target session has at least `DISCOVERY.md` or `PLAN.md` — bare `SESSION.md` is skipped.

## Default Usage

Run the deterministic preview first:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest/ingest_sessions.py latest --dry-run
```

If the preview looks right, run the real ingest:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest/ingest_sessions.py latest
```

Specific session:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest/ingest_sessions.py ~/src/.ai/sessions/2026-04-10_ENT-1240_Taxonomy-Codes
```

Different group (ingesting ADRs / READMEs):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest/ingest_sessions.py <path> --group codebase-docs
```

## Cost Controls (zero-token modes)

| Flag | Purpose |
|---|---|
| `--dry-run` | Preview the episode (name, body excerpt, group_id, reference_time) without calling Graphiti |
| `--estimate` | Token count × model price; warn before committing |
| `--validate-only` | Check body is non-empty and under the 8K soft cap |

All three cost zero LLM tokens.

## What Gets Extracted

| Entity | From |
|---|---|
| `Decision` | DISCOVERY.md and PLAN.md text — "we decided X because Y" |
| `Problem` | DISCOVERY.md "gaps" / "issues" sections and SESSION.md error discussion |
| `TechChoice` | PLAN.md dependency lists and "Tech Stack" sections |
| `Session` | Always one per ingest; carries the ticket / slug / phase_reached |

## Skill Behavior

When this skill fires:

1. Run `ingest_sessions.py <target> --dry-run` and show the preview.
2. If the user confirms (or in auto mode, proceed), run the real ingest.
3. Report the returned `episode_uuid`, `nodes_extracted`, `edges_extracted`.
4. If the session has no DISCOVERY.md / PLAN.md, emit a skip message — do not attempt ingest.

## See Also

- [`references/session-conventions.md`](../session-handoff/references/session-conventions.md) — what makes a session ingestable
- [`docs/setup.md`](../../docs/setup.md) — Graphiti + LLM provider setup
- [`docs/mcp-config.md`](../../docs/mcp-config.md) — MCP server for `/query`
