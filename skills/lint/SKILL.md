---
name: lint
description: Run deterministic health checks over the Graphiti graph and the rendered wiki. Flags isolated nodes, stale pages, and render/graph divergence. Use when the user asks "what's broken in the wiki" or on a weekly cadence.
---

# /lint

Calls `scripts/view/lint.py`. The script itself is fully deterministic — this skill exists only so `/lint --explain` can layer LLM remediation advice on top of the raw findings.

## Default Usage (zero LLM tokens)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/lint.py
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/lint.py --pretty
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/lint.py --max-age-days 14
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/lint.py --no-graph  # filesystem only
```

## Checks

| Check | What it catches | Why Graphiti does not do this |
|---|---|---|
| `stale_page` | Rendered `.md` files older than `--max-age-days` (default 30) | Files are a view, not graph state |
| `isolated_node` | Entities extracted with zero edges | Zero-edge is a *quality* signal, not a contradiction |
| `divergence` | Pages whose `source_uuid` no longer resolves to a live node | Temporal invalidation marks nodes invalid but leaves files untouched |

Supersession / contradiction detection is **not** in scope — Graphiti's temporal invalidation handles that natively via `valid_at` / `invalid_at` edges, which `/query` already surfaces.

## Explain Mode (opt-in, costs LLM tokens)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/view/lint.py --explain
```

The Python script returns `exit 2` for `--explain` because the LLM synthesis step has to happen inside Claude Code. When the user passes `--explain`, this skill:

1. Runs `lint.py` without `--explain` to collect the raw JSON findings.
2. For each finding, asks the LLM for a one- or two-sentence remediation written for a human reader — what the warning means and the concrete next step.
3. Emits a combined report: raw finding + LLM prose per entry.

Use this sparingly. The default (deterministic) mode is sufficient for weekly health checks.

## Scheduling

Deterministic mode can run on a cron or as a git pre-push hook:

```cron
# Weekly Monday-morning wiki lint, JSON log appended
0 9 * * 1 python3 /path/to/ephemeris/scripts/view/lint.py --pretty >> ~/.ai/ephemeris/lint.log 2>&1
```

## Skill Behavior

1. Run the script in default JSON mode unless the user asked for `--pretty` or `--explain`.
2. Summarize the findings in one short paragraph before showing any table.
3. If there are zero findings, say "OK — no findings." and stop.
4. For `--explain`, layer prose remediation over the raw JSON per the algorithm above.

## See Also

- [`../render/SKILL.md`](../render/SKILL.md) — the script that produces the pages `/lint` checks
- [`../../docs/token-efficiency.md`](../../docs/token-efficiency.md) — why the default path avoids LLM calls
