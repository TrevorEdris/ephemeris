# Session Directory Conventions

Session root: `~/src/.ai/`

Create a new directory within `~/src/.ai/sessions/` with the format `YYYY-MM-DD_<JIRA>_<TITLE_SLUG>/`.

Example: `~/src/.ai/sessions/2026-01-22_ENT-1240_Taxonomy-Codes/`

If no ticket is available, use a descriptive slug: `~/src/.ai/sessions/2026-01-22_Refactor-Error-Handling/`.

## Required Files

### SESSION.md

- Document user prompts and summarized responses.
- Explicitly list every question asked and its answer.
- Append as the session progresses — do not rewrite.

### DISCOVERY.md

Created during the Discover phase. Contents:

- Current state analysis
- Identified gaps, issues, requirements
- Data model and API coverage analysis

Each research question answered with code evidence (file:line references).

### PLAN.md

Created during the Plan phase, before implementation. Contents:

- Target repos and file paths
- Ordered implementation steps (2–5 min each)
- Risks and assumptions
- Verification steps for each step
- Git strategy (branch, commit checkpoints, PR title/body)

### INDEX.md

Lives at `~/src/.ai/sessions/INDEX.md`, maintained by `/session-index`.

- Run `/session-index generate` periodically to update the cross-session index.
- Use `/session-index link` to record blocking relationships between sessions.

## Why

Sessions are the raw substrate that `/ingest` feeds into the Graphiti knowledge graph. Consistent structure lets the ingest script extract entities reliably without per-session heuristics.
