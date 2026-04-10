# Token Efficiency

Reference for keeping context lean and output quality high.

## Phase-Scoped Reference Loading

When working with skills that declare a `context-manifest` in their SKILL.md frontmatter:

1. During Discover phase: load only `always` + `discover` references.
2. During Plan phase: load only `always` + `plan` references.
3. During Implement phase: load only `always` + `implement` references.
4. Do not load references for inactive phases unless explicitly needed.

ephemeris skills follow this convention where it applies; the `references/` directory is intentionally phase-scoped per skill.

## Compaction Controls

**Set the compaction threshold earlier** to preserve output quality:

```bash
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60
```

Default triggers at 80%. At 60%, Claude still has headroom and produces better output than when the window is nearly full.

**Compact manually at natural milestones** — after Discover, after Plan approval, after each implementation phase. Use `/compact Focus on decisions made, not the reasoning process` to guide what survives.

**Use `/clear` when switching topics** entirely. Claude re-reads CLAUDE.md fresh, costing ~2K tokens instead of carrying stale context.

## Output Format

Structured output costs 40–70% fewer tokens than prose for equivalent information:

- Prefer bullets and tables over paragraphs.
- Prefer JSON over narrative when producing structured data.
- Never ask Claude to "explain" something that can be expressed as a table.

## Subagent Model Tiers

Each subagent invocation carries ~20K baseline overhead (system prompt + tool descriptions). Match the model to the task:

| Task | Model |
|------|-------|
| File search, listing, simple grep | `haiku` |
| Feature implementation, bug fix | `sonnet` |
| Architecture, security audit, complex refactor | `opus` |

Set `model: haiku` in agent frontmatter for reconnaissance agents.

## ephemeris-Specific Savings

Several ephemeris operations were extracted to Python scripts specifically to eliminate token cost:

| Operation | Token cost | How |
|---|---|---|
| `scripts/view/lint.py` (default) | 0 | Deterministic graph queries + file stat; no LLM |
| `scripts/view/render.py` (default) | 0 | Jinja2 templates, no LLM |
| `scripts/ingest/*.py --dry-run` | 0 | Preview episodes without calling `add_episode()` |
| `scripts/ingest/*.py --estimate` | 0 | Count episodes × tokens × model price before committing |
| `scripts/ingest/*.py --validate-only` | 0 | Check episode bodies before LLM extraction |
| `workflow_phase_reminder.py` hook | ~100/prompt | Brief phase-specific reminder vs ~2000 for full rule |

LLM operations that remain:

- `add_episode()` entity/edge extraction — the core Graphiti feature.
- `/query` answer synthesis — temporal reasoning over graph results.
- `/lint --explain` remediation prose — opt-in only.
- `/render --narrated` — opt-in only.

## Monitoring Tools

- `/context` — live token allocation breakdown.
- `npx ccusage` — CLI analysis of JSONL session files.
