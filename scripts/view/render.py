#!/usr/bin/env python3
"""Render a Graphiti group to browsable markdown under ~/.ai/ephemeris/wiki/.

Two modes:

    default:    Jinja2 templates, zero LLM calls, fully deterministic.
    --narrated: LLM synthesizes prose summaries instead of template bullets.

The default path is preferred — see docs/token-efficiency.md. The narrated
path exists for polished human-readable output and is opt-in only.

The data-fetch and file-write layers are separated so tests can exercise the
pure template rendering without hitting Graphiti.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from schema import WORKFLOW_GROUP

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_WIKI_ROOT = Path.home() / ".ai" / "ephemeris" / "wiki"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Lowercase, punctuation-stripped slug for filenames."""
    slug = _SLUG_RE.sub("-", title.strip().lower()).strip("-")
    return slug or "untitled"


def make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
        keep_trailing_newline=True,
    )


def group_by_type(entities: list[dict]) -> dict[str, list[dict]]:
    """Group the fetched entities by their ``entity_type`` key."""
    out: dict[str, list[dict]] = {}
    for e in entities:
        out.setdefault(e["entity_type"], []).append(e)
    for pages in out.values():
        pages.sort(key=lambda e: e["title"].lower())
    return out


def render_entity_page(
    env: Environment,
    entity: dict,
    *,
    group_id: str,
    generated: str,
) -> str:
    tmpl = env.get_template("entity.md.j2")
    return tmpl.render(
        entity_type=entity["entity_type"],
        group_id=group_id,
        tags=entity.get("tags", []),
        generated=generated,
        graph_query=(
            f"search_nodes(query='{entity['title']}', "
            f"entity_types=['{entity['entity_type']}'])"
        ),
        source_uuid=entity["uuid"],
        title=entity["title"],
        summary=entity.get("summary", ""),
        fields=entity.get("fields", {}),
        related=entity.get("related", []),
    )


def render_index_page(
    env: Environment,
    entities: list[dict],
    *,
    group_id: str,
    generated: str,
) -> str:
    grouped = group_by_type(entities)
    by_type = {}
    for entity_type, pages in grouped.items():
        by_type[entity_type] = [
            {
                "title": p["title"],
                "href": f"{entity_type}/{slugify(p['title'])}.md",
            }
            for p in pages
        ]
    tmpl = env.get_template("index.md.j2")
    return tmpl.render(
        generated=generated,
        group_id=group_id,
        total=len(entities),
        by_type=by_type,
    )


def render_log_entry(
    env: Environment,
    *,
    group_id: str,
    generated: str,
    written: int,
    updated: int,
    total: int,
) -> str:
    tmpl = env.get_template("log.md.j2")
    return tmpl.render(
        generated=generated,
        group_id=group_id,
        written=written,
        updated=updated,
        total=total,
    )


def write_pages(
    env: Environment,
    entities: list[dict],
    wiki_root: Path,
    group_id: str,
    generated: str,
) -> dict:
    """Write all pages + index + log. Returns counts for the log entry."""
    wiki_root.mkdir(parents=True, exist_ok=True)
    written = 0
    updated = 0
    for entity in entities:
        page = render_entity_page(
            env, entity, group_id=group_id, generated=generated
        )
        type_dir = wiki_root / entity["entity_type"]
        type_dir.mkdir(parents=True, exist_ok=True)
        out = type_dir / f"{slugify(entity['title'])}.md"
        if out.exists():
            existing = out.read_text()
            # Compare without the frontmatter generated timestamp so rerenders
            # without content changes don't count as updates.
            if _strip_generated(existing) == _strip_generated(page):
                continue
            out.write_text(page)
            updated += 1
        else:
            out.write_text(page)
            written += 1

    index_page = render_index_page(
        env, entities, group_id=group_id, generated=generated
    )
    (wiki_root / "index.md").write_text(index_page)

    log_path = wiki_root / "log.md"
    log_entry = render_log_entry(
        env,
        group_id=group_id,
        generated=generated,
        written=written,
        updated=updated,
        total=len(entities),
    )
    if log_path.exists():
        log_path.write_text(log_path.read_text() + log_entry)
    else:
        log_path.write_text(f"# Render Log\n\n{log_entry}")

    return {"written": written, "updated": updated, "total": len(entities)}


_GEN_LINE_RE = re.compile(r"^generated: .*$", re.MULTILINE)


def _strip_generated(page: str) -> str:
    return _GEN_LINE_RE.sub("generated: <omitted>", page)


async def fetch_entities(group_id: str) -> list[dict]:
    """Fetch entities from Graphiti for ``group_id``.

    This requires a live Graphiti + backing store and is therefore excluded
    from unit tests. Tests call ``write_pages`` directly with fixture data.
    """
    from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF  # noqa: PLC0415

    from ingest.graphiti_client import get_graphiti  # noqa: PLC0415

    graphiti = await get_graphiti()
    config = NODE_HYBRID_SEARCH_RRF
    result = await graphiti._search(
        query="*", group_ids=[group_id], config=config, limit=200
    )

    entities: list[dict] = []
    for node in result.nodes:
        fields = getattr(node, "attributes", {}) or {}
        entity_type = None
        if getattr(node, "labels", None):
            for label in node.labels:
                if label != "Entity":
                    entity_type = label
                    break
        if entity_type is None:
            entity_type = "Entity"
        entities.append(
            {
                "uuid": str(node.uuid),
                "entity_type": entity_type,
                "title": getattr(node, "name", str(node.uuid)),
                "fields": dict(fields),
                "tags": [],
                "summary": getattr(node, "summary", "") or "",
                "related": [],
            }
        )
    return entities


async def render_group(
    group_id: str, wiki_root: Path, *, narrated: bool = False
) -> dict:
    env = make_env()
    entities = await fetch_entities(group_id)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if narrated:
        print(
            "error: --narrated mode requires the /render skill (LLM synthesis)",
            file=sys.stderr,
        )
        return {"written": 0, "updated": 0, "total": 0}
    return write_pages(env, entities, wiki_root, group_id, generated)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--group", default=WORKFLOW_GROUP, help="Graphiti group_id to render"
    )
    parser.add_argument(
        "--wiki-root",
        default=str(DEFAULT_WIKI_ROOT),
        help="Output root (default: ~/.ai/ephemeris/wiki/)",
    )
    parser.add_argument("--narrated", action="store_true", help="Opt-in LLM mode")
    args = parser.parse_args(argv)

    result = asyncio.run(
        render_group(
            args.group,
            Path(args.wiki_root).expanduser(),
            narrated=args.narrated,
        )
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
