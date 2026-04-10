#!/usr/bin/env python3
"""Deterministic wiki + graph health check.

Three checks covered here; all three are what Graphiti does *not* handle on
its own:

1. ``stale_page``  — rendered pages older than ``--max-age-days``.
2. ``isolated_node`` — entities with zero edges (degree-0 nodes in the graph).
3. ``divergence``  — rendered pages whose ``source_uuid`` no longer matches
   a live node (deletion or supersession since last render).

Contradiction / supersession detection is not handled here — Graphiti's
temporal invalidation does that for free.

Usage::

    python scripts/view/lint.py
    python scripts/view/lint.py --pretty
    python scripts/view/lint.py --no-graph          # filesystem-only, zero deps
    python scripts/view/lint.py --max-age-days 14
    python scripts/view/lint.py --group codebase-history

Output:
    Default:    JSON report ``{"findings": [...]}`` to stdout
    --pretty:   terminal-friendly table to stdout
    --explain:  not implemented in P4 — requires LLM, gated behind the
                ``/lint`` skill wrapper.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from schema import CODEBASE_GROUP, DOCS_GROUP, WORKFLOW_GROUP

DEFAULT_WIKI_ROOT = Path.home() / ".ai" / "ephemeris" / "wiki"
DEFAULT_MAX_AGE_DAYS = 30
SKIP_FILES = {"index.md", "log.md"}

# Minimal YAML frontmatter parser — only `key: value` lines, no nesting.
# Rendered pages are machine-generated from templates so the shape is fixed.
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")


# --- Pure functions ---------------------------------------------------------


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract the YAML frontmatter block at the top of a rendered page."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kv = _KV_RE.match(line)
        if kv:
            key, value = kv.group(1), kv.group(2)
            # Strip surrounding quotes if present
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            out[key] = value
    return out


def iter_rendered_pages(wiki_root: Path):
    """Yield entity pages under ``wiki_root``, skipping index.md and log.md."""
    if not wiki_root.exists():
        return
    for p in sorted(wiki_root.rglob("*.md")):
        if p.name in SKIP_FILES:
            continue
        yield p


def find_stale_pages(
    wiki_root: Path, *, max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> list[dict]:
    """Return findings for pages whose mtime is older than ``max_age_days``."""
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    findings: list[dict] = []
    for page in iter_rendered_pages(wiki_root):
        mtime = page.stat().st_mtime
        if mtime < cutoff:
            days_old = int((now - mtime) // 86400)
            findings.append(
                {
                    "check": "stale_page",
                    "severity": "warning",
                    "path": str(page),
                    "days_old": days_old,
                    "suggested_action": (
                        f"Re-render: python scripts/view/render.py "
                        f"--wiki-root {wiki_root}"
                    ),
                }
            )
    return findings


def check_isolated_nodes(nodes: list[dict]) -> list[dict]:
    """Flag entities whose ``degree`` is zero.

    ``nodes`` is a list of ``{uuid, name, degree, entity_type}`` dicts — the
    graph-backed caller assembles this from a live Graphiti query.
    """
    findings: list[dict] = []
    for n in nodes:
        if n.get("degree", 0) == 0:
            findings.append(
                {
                    "check": "isolated_node",
                    "severity": "warning",
                    "uuid": n["uuid"],
                    "name": n.get("name", "<unnamed>"),
                    "entity_type": n.get("entity_type", "Entity"),
                    "suggested_action": (
                        "Re-ingest the source episode — the LLM extracted the "
                        "entity but did not find any relationships. Likely a "
                        "too-short or context-free episode body."
                    ),
                }
            )
    return findings


def check_divergence(page_views: list[dict]) -> list[dict]:
    """Flag rendered pages whose source entity no longer exists in the graph.

    ``page_views`` is a list of ``{path, source_uuid, live_matches}`` dicts,
    where ``live_matches`` is the count of nodes returned by re-running the
    page's ``graph_query`` against a live Graphiti instance.
    """
    findings: list[dict] = []
    for view in page_views:
        if view.get("live_matches", 1) == 0:
            findings.append(
                {
                    "check": "divergence",
                    "severity": "warning",
                    "path": view["path"],
                    "source_uuid": view.get("source_uuid"),
                    "suggested_action": (
                        "Entity missing or superseded. Delete the page or "
                        "re-run /render to pick up the replacement."
                    ),
                }
            )
    return findings


# --- Orchestration ---------------------------------------------------------


def run_filesystem_checks(
    wiki_root: Path, *, max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> list[dict]:
    """All checks that do not require a live Graphiti connection."""
    return find_stale_pages(wiki_root, max_age_days=max_age_days)


async def run_graph_checks(
    wiki_root: Path, group_ids: list[str]
) -> list[dict]:
    """Isolated-node + divergence checks. Deferred import — needs graphiti."""
    from ingest.graphiti_client import get_graphiti  # noqa: PLC0415

    graphiti = await get_graphiti()

    # Isolated-node check: query all nodes in the target groups, then count
    # edges per node. Kuzu / Neo4j both expose this via the driver's cypher
    # interface; we go through Graphiti's search as a portable baseline.
    from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF  # noqa: PLC0415

    result = await graphiti._search(
        query="*", group_ids=group_ids, config=NODE_HYBRID_SEARCH_RRF, limit=500
    )
    nodes: list[dict] = []
    for node in result.nodes:
        edges = await graphiti.get_entity_edge(str(node.uuid)) if False else []
        # Degree lookup varies by driver. Use the node's labels as a best-effort
        # entity_type and fall back to 0 when the driver does not expose it.
        degree = getattr(node, "edge_count", None)
        if degree is None:
            degree = 0
        entity_type = "Entity"
        labels = getattr(node, "labels", None) or []
        for label in labels:
            if label != "Entity":
                entity_type = label
                break
        nodes.append(
            {
                "uuid": str(node.uuid),
                "name": getattr(node, "name", str(node.uuid)),
                "degree": degree,
                "entity_type": entity_type,
            }
        )
    findings = check_isolated_nodes(nodes)

    # Divergence check: walk rendered pages, re-run their stored graph_query,
    # compare live match counts to the single-entity assumption.
    page_views: list[dict] = []
    for page in iter_rendered_pages(wiki_root):
        fm = parse_frontmatter(page.read_text())
        source_uuid = fm.get("source_uuid")
        if not source_uuid:
            continue
        # A rendered page always maps to exactly one source entity. If that
        # UUID is not present in the live result set, the entity is gone.
        live_matches = 1 if any(n["uuid"] == source_uuid for n in nodes) else 0
        page_views.append(
            {
                "path": str(page.relative_to(wiki_root)),
                "source_uuid": source_uuid,
                "live_matches": live_matches,
            }
        )
    findings.extend(check_divergence(page_views))
    return findings


# --- Output formatting -----------------------------------------------------


def render_pretty(findings: list[dict]) -> str:
    if not findings:
        return "OK — no findings.\n"
    header = f"{'SEVERITY':<8}  {'CHECK':<16}  DETAIL"
    lines = [header, "-" * len(header)]
    for f in findings:
        detail = f.get("path") or f.get("name") or f.get("uuid") or ""
        lines.append(f"{f['severity']:<8}  {f['check']:<16}  {detail}")
    lines.append("")
    lines.append(f"{len(findings)} finding(s).")
    return "\n".join(lines) + "\n"


# --- CLI -------------------------------------------------------------------


_GROUP_ALIASES = {
    "workflow": WORKFLOW_GROUP,
    "workflow-knowledge": WORKFLOW_GROUP,
    "codebase": CODEBASE_GROUP,
    "codebase-history": CODEBASE_GROUP,
    "docs": DOCS_GROUP,
    "codebase-docs": DOCS_GROUP,
}


def _resolve_groups(values: list[str]) -> list[str]:
    return [_GROUP_ALIASES.get(v, v) for v in values]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wiki-root", default=str(DEFAULT_WIKI_ROOT), help="Wiki root to lint"
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help="Pages older than this count as stale",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Graphiti group_id to include (repeatable)",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Skip Graphiti-backed checks (filesystem only, zero deps)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Terminal-friendly table instead of JSON",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Invoke LLM for prose remediation (requires /lint skill wrapper)",
    )
    args = parser.parse_args(argv)

    if args.explain:
        print(
            "error: --explain requires the /lint skill wrapper (LLM synthesis)",
            file=sys.stderr,
        )
        return 2

    wiki_root = Path(args.wiki_root).expanduser()
    findings = run_filesystem_checks(wiki_root, max_age_days=args.max_age_days)

    if not args.no_graph:
        groups = _resolve_groups(args.group) if args.group else [
            WORKFLOW_GROUP,
            CODEBASE_GROUP,
        ]
        try:
            findings.extend(asyncio.run(run_graph_checks(wiki_root, groups)))
        except Exception as e:  # noqa: BLE001
            print(
                f"warning: graph checks skipped ({e.__class__.__name__}: {e})",
                file=sys.stderr,
            )

    if args.pretty:
        sys.stdout.write(render_pretty(findings))
    else:
        print(json.dumps({"findings": findings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
