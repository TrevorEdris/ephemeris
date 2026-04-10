# Setup

## 1. LLM Provider (Required)

**Every `add_episode()` call runs LLM inference.** Without an API key configured, ingest silently fails or errors out. Configure this *first*.

### OpenAI (default)

```bash
export OPENAI_API_KEY=sk-...
```

Graphiti uses `gpt-4o-mini` by default — a reasonable baseline for structured extraction.

### Anthropic

Pass an `AnthropicClient` at Graphiti init:

```python
from graphiti_core import Graphiti
from graphiti_core.llm_client.anthropic_client import AnthropicClient

graphiti = Graphiti(driver, llm_client=AnthropicClient())
```

Set the key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Model Selection for Batch Ingest

For large codebase-history ingests (P7a), configure a cheap model — `haiku` via Anthropic or `gpt-4o-mini` via OpenAI. ~15× cheaper than Sonnet/GPT-4o and acceptable for structured extraction from commit text.

Model selection happens at client init, not via env var.

## 2. Backing Store — Kuzu (default)

Embedded, zero-server, single-file. Best for dev and single-user.

```bash
pip install "graphiti-core[kuzu]"
```

Default DB path: `~/.ai/ephemeris/db`. Override with `EPHEMERIS_DB_PATH`.

Kuzu does not support multi-writer access — use Neo4j or FalkorDB if multiple ingest processes run concurrently.

## 3. Backing Store — Neo4j (team-shared)

```bash
pip install "graphiti-core[neo4j]"
```

```yaml
# docker-compose.yml
services:
  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j-data:/data

volumes:
  neo4j-data:
```

```bash
docker compose up -d
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
```

## 4. Backing Store — FalkorDB (alternative)

```bash
pip install "graphiti-core[falkordb]"
```

```yaml
services:
  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - "6379:6379"
```

## 5. Python Dependencies

```bash
cd ~/src/github.com/TrevorEdris/ephemeris
pip install -e ".[dev]"
```

This installs `graphiti-core[kuzu]`, `jinja2`, `pydantic`, `pytest`, `pytest-asyncio`.

## 6. Install as Claude Code Plugin

```bash
claude plugin install ~/src/github.com/TrevorEdris/ephemeris
```

Verify skills are visible:

```bash
# In a Claude Code session
/ingest    # should be discovered
/query
/render
/lint
```

## 7. MCP Server

See [mcp-config.md](mcp-config.md).

## Environment Variables Reference

| Variable | Default | Used by |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | All `add_episode` calls (LLM extraction) |
| `EPHEMERIS_DB_PATH` | `~/.ai/ephemeris/db` | Kuzu driver (`scripts/ingest/graphiti_client.py`) |
| `EPHEMERIS_STATE_ROOT` | `~/.ai/ephemeris/state` | `mark_ingested()` + `hooks/session_ingest.py` (ingest dedup) |
| `EPHEMERIS_SESSIONS_ROOT` | `~/src/.ai/sessions` | `hooks/workflow_phase_reminder.py`, `hooks/session_ingest.py` |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | — | Neo4j driver only |

All of these can be overridden per-session via a shell export, a `.env` file, or the `env` block in `~/.claude/settings.json` for MCP server isolation.

## Migration Path — Kuzu → Neo4j

No in-place migration. Re-ingest from source artifacts:

```bash
# 1. Export the state files (ingest dedup markers)
cp ~/.ai/ephemeris/state/ingested-sessions.json /tmp/
cp ~/.ai/ephemeris/state/ingested-tickets.json /tmp/

# 2. Wipe the Kuzu DB and state
rm -rf ~/.ai/ephemeris/db ~/.ai/ephemeris/state

# 3. Configure Neo4j (step 3 above)

# 4. Re-ingest
python scripts/ingest/ingest_sessions.py latest
python scripts/ingest/ingest_codebase.py --since "6 months ago"
```
