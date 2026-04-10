# MCP Configuration

ephemeris uses the [Graphiti MCP server](https://github.com/getzep/graphiti) for `/query` and any runtime entity lookups. Graphiti exposes a simplified MCP surface — not all Python-API features are available via MCP.

## Install the MCP Server

```bash
pip install graphiti-mcp-server
```

## Wire into Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "graphiti": {
      "command": "graphiti-mcp-server",
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "GRAPHITI_DB_PATH": "~/.ai/ephemeris/db"
      }
    }
  }
}
```

Restart Claude Code. The following tools should appear:

| Tool | Parameters | Notes |
|---|---|---|
| `add_memory` | `name, episode_body, group_id?, source?, source_description?, uuid?` | Queues episode for background processing (async) |
| `search_nodes` | `query, group_ids?, max_nodes?, entity_types?` | Natural-language entity search |
| `search_memory_facts` | `query, group_ids?, max_facts?, center_node_uuid?` | Relationship / fact search |
| `get_episodes` | `group_ids?, max_episodes?` | List stored episodes |
| `get_entity_edge` | `uuid` | Fetch a specific relationship |
| `delete_entity_edge` | `uuid` | Remove a relationship |
| `delete_episode` | `uuid` | Remove an episode |
| `clear_graph` | `group_ids?` | Wipe graph data |
| `get_status` | — | Health check |

## MCP Limitations vs Python API

The MCP `add_memory` tool is a simplified wrapper. It does **not** expose:

- `entity_types` — custom Pydantic entity types
- `edge_types` — custom Pydantic edge types
- `reference_time` — explicit episode timestamp
- `previous_episode_uuids` — episode linking

Rich ingest (custom types, temporal ordering, episode linking) **must** use the Python API directly via the ephemeris ingest scripts. `add_memory` is also queued — entities may not be immediately queryable after the call returns.

## Which Path to Use

| Operation | Path | Why |
|---|---|---|
| Bulk ingest of sessions / git / Jira | Python API (`scripts/ingest/*.py`) | Custom types + temporal linking required |
| `/query` natural-language search | MCP (`search_nodes`, `search_memory_facts`) | Sufficient; no LLM extraction happening |
| `/render` default mode | Python API | Needs to iterate entities by type |
| `/render --narrated` | MCP search + LLM synthesis | Search-only; writes are not needed |

## Non-Claude MCP Clients

The Graphiti MCP server speaks standard MCP — Cursor, Windsurf, or any MCP-supporting client can connect to the same server. ephemeris Python scripts and the MCP server are therefore tool-agnostic; only the skills, hooks, and agents are Claude Code specific.
