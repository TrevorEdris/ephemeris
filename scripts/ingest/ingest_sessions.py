#!/usr/bin/env python3
"""Ingest a session directory into Graphiti's workflow-knowledge group.

Deterministic operations (parsing, validation, preview, cost estimate) run
without touching Graphiti or any LLM. Only the final ``add_episode()`` call
requires a live Graphiti client and an LLM API key.

Usage:
    python ingest_sessions.py <session-dir>
    python ingest_sessions.py latest
    python ingest_sessions.py latest --dry-run
    python ingest_sessions.py latest --estimate
    python ingest_sessions.py latest --validate-only
    python ingest_sessions.py <session-dir> --group codebase-docs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from schema import CODEBASE_GROUP, DOCS_GROUP, EDGE_TYPES, ENTITY_TYPES_WORKFLOW, WORKFLOW_GROUP

SESSIONS_ROOT = Path.home() / "src" / ".ai" / "sessions"

# Matches YYYY-MM-DD_<OPTIONAL TICKET>_<SLUG> session dir names.
# Ticket is [A-Z]+-\d+; absent means the slug starts immediately after the date.
SESSION_DIR_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?:(?P<ticket>[A-Z]+-\d+)_)?(?P<slug>.+)$"
)

# Canonical concatenation order — SESSION first (prompts/responses),
# then DISCOVERY (findings), then PLAN (decisions).
CANONICAL_FILES = ("SESSION.md", "DISCOVERY.md", "PLAN.md")

# Rough token estimate: ~4 chars/token for English prose.
CHARS_PER_TOKEN = 4
# gpt-4o-mini price per 1M input tokens as of 2026-04 (docs/setup.md recommends this).
MODEL_USD_PER_MTOK = 0.15


@dataclass
class SessionInfo:
    path: Path
    date: date
    ticket: str | None
    slug: str


def parse_session_dir(path: Path) -> SessionInfo:
    """Extract date / ticket / slug from a session dir name."""
    m = SESSION_DIR_RE.match(path.name)
    if not m:
        raise ValueError(
            f"Session dir does not match YYYY-MM-DD_[TICKET_]SLUG format: {path.name}"
        )
    return SessionInfo(
        path=path,
        date=datetime.strptime(m.group("date"), "%Y-%m-%d").date(),
        ticket=m.group("ticket"),
        slug=m.group("slug"),
    )


def read_session_files(path: Path) -> str:
    """Concatenate canonical files in order, each under its own header.

    Files that exist but are empty (after stripping whitespace) are omitted
    entirely so that downstream validation does not see a body that is
    nothing but section headers.
    """
    parts: list[str] = []
    for name in CANONICAL_FILES:
        f = path / name
        if not f.exists():
            continue
        body = f.read_text()
        if not body.strip():
            continue
        parts.append(f"# {name}\n\n{body}")
    return "\n\n".join(parts)


def is_ingestable(path: Path) -> bool:
    """Sessions are only worth ingesting once they have DISCOVERY or PLAN.

    A bare SESSION.md (just the prompt log) yields low-signal extraction.
    """
    return (path / "DISCOVERY.md").exists() or (path / "PLAN.md").exists()


def resolve_latest(root: Path) -> Path:
    """Return the most recent session dir under ``root``."""
    candidates = [
        p
        for p in root.iterdir()
        if p.is_dir() and SESSION_DIR_RE.match(p.name)
    ]
    if not candidates:
        raise FileNotFoundError(f"No session dirs found under {root}")
    return max(candidates, key=lambda p: p.name)


def build_episode_preview(path: Path) -> dict:
    """Return a serializable preview of what would be sent to ``add_episode``."""
    info = parse_session_dir(path)
    body = read_session_files(path)
    excerpt_len = 400
    return {
        "name": path.name,
        "group_id": WORKFLOW_GROUP,
        "source_description": ".ai/sessions",
        "reference_time": info.date.isoformat(),
        "ticket": info.ticket,
        "slug": info.slug,
        "episode_body_bytes": len(body),
        "episode_body_excerpt": body[:excerpt_len],
    }


def estimate_cost(body: str) -> dict:
    tokens = max(1, len(body) // CHARS_PER_TOKEN)
    cost_usd = (tokens / 1_000_000) * MODEL_USD_PER_MTOK
    return {
        "estimated_tokens": tokens,
        "estimated_cost_usd": round(cost_usd, 6),
        "model_assumed": "gpt-4o-mini",
        "usd_per_mtok": MODEL_USD_PER_MTOK,
    }


def validate_body(body: str) -> list[str]:
    """Return a list of validation errors; empty list = valid."""
    errors: list[str] = []
    if not body.strip():
        errors.append("Episode body is empty (no content in SESSION/DISCOVERY/PLAN).")
    # Graphiti has an effective ~8K token cap for extraction. Warn, do not block.
    approx_tokens = len(body) // CHARS_PER_TOKEN
    if approx_tokens > 8000:
        errors.append(
            f"Episode body is {approx_tokens} estimated tokens — exceeds 8K soft cap. "
            "Consider splitting."
        )
    return errors


def resolve_target(arg: str) -> Path:
    if arg == "latest":
        return resolve_latest(SESSIONS_ROOT)
    return Path(arg).expanduser().resolve()


def group_id_for(arg: str) -> str:
    mapping = {
        "workflow": WORKFLOW_GROUP,
        "workflow-knowledge": WORKFLOW_GROUP,
        "codebase": CODEBASE_GROUP,
        "codebase-history": CODEBASE_GROUP,
        "docs": DOCS_GROUP,
        "codebase-docs": DOCS_GROUP,
    }
    return mapping.get(arg, arg)


def _state_dir() -> Path:
    override = os.environ.get("EPHEMERIS_STATE_ROOT")
    return Path(override) if override else Path.home() / ".ai" / "ephemeris" / "state"


def mark_ingested(session_name: str) -> None:
    """Append ``session_name`` to the ingested-sessions state file.

    Read by ``hooks/session_ingest.py`` so the auto-ingest prompt does not
    re-nag on sessions that have already been processed. Idempotent.
    """
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "ingested-sessions.json"
    existing: list[str] = []
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            if isinstance(data, list):
                existing = [str(x) for x in data]
        except (json.JSONDecodeError, OSError):
            existing = []
    if session_name not in existing:
        existing.append(session_name)
        state_file.write_text(json.dumps(existing, indent=2))


async def ingest_session(path: Path, group_id: str = WORKFLOW_GROUP) -> None:
    """Call Graphiti's ``add_episode`` for a real ingest.

    This path requires ``graphiti-core[kuzu]`` installed and an LLM API key.
    Deferred imports keep the deterministic paths fast and dep-free.
    """
    from graphiti_core.nodes import EpisodeType  # noqa: PLC0415

    from ingest.graphiti_client import get_graphiti  # noqa: PLC0415

    info = parse_session_dir(path)
    body = read_session_files(path)
    graphiti = await get_graphiti()
    result = await graphiti.add_episode(
        name=path.name,
        episode_body=body,
        source_description=".ai/sessions",
        reference_time=datetime.combine(info.date, datetime.min.time()),
        source=EpisodeType.text,
        group_id=group_id,
        entity_types=ENTITY_TYPES_WORKFLOW,
        edge_types=EDGE_TYPES,
    )
    mark_ingested(path.name)
    print(
        json.dumps(
            {
                "episode_uuid": str(result.episode.uuid),
                "nodes_extracted": len(result.nodes),
                "edges_extracted": len(result.edges),
                "group_id": group_id,
            }
        )
    )


async def ingest_text_episode(*, name: str, body: str, group_id: str) -> None:
    """Ingest a literal text episode (the /query 'file this answer' path).

    Uses the Python API for the same reason the session path does: MCP
    ``add_memory`` does not expose ``entity_types`` / ``edge_types``.
    """
    from graphiti_core.nodes import EpisodeType  # noqa: PLC0415

    from ingest.graphiti_client import get_graphiti  # noqa: PLC0415

    graphiti = await get_graphiti()
    result = await graphiti.add_episode(
        name=name,
        episode_body=body,
        source_description="/query",
        reference_time=datetime.combine(date.today(), datetime.min.time()),
        source=EpisodeType.text,
        group_id=group_id,
        entity_types=ENTITY_TYPES_WORKFLOW,
        edge_types=EDGE_TYPES,
    )
    print(
        json.dumps(
            {
                "episode_uuid": str(result.episode.uuid),
                "nodes_extracted": len(result.nodes),
                "edges_extracted": len(result.edges),
                "group_id": group_id,
            }
        )
    )


def build_text_episode_preview(*, name: str, body: str, group_id: str) -> dict:
    """Preview for the /query 'file this answer' path — no session dir."""
    excerpt_len = 400
    return {
        "name": name,
        "group_id": group_id,
        "source_description": "/query",
        "reference_time": date.today().isoformat(),
        "episode_body_bytes": len(body),
        "episode_body_excerpt": body[:excerpt_len],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        help="Session dir path, or 'latest'. Omit when using --episode-text.",
    )
    parser.add_argument("--group", default="workflow", help="Group ID override")
    parser.add_argument(
        "--episode-text",
        help="Ingest a synthetic episode from this literal text (used by /query).",
    )
    parser.add_argument(
        "--name",
        help="Episode name. Required with --episode-text.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview episode; no LLM call")
    mode.add_argument("--estimate", action="store_true", help="Token + cost estimate; no LLM call")
    mode.add_argument("--validate-only", action="store_true", help="Validate body; no LLM call")
    args = parser.parse_args(argv)

    # --- Synthetic episode path (/query 'file this answer') ----------------
    if args.episode_text is not None:
        if not args.name:
            print("error: --episode-text requires --name", file=sys.stderr)
            return 2
        group_id = group_id_for(args.group)
        body = args.episode_text

        if args.validate_only:
            errors = validate_body(body)
            if errors:
                for e in errors:
                    print(f"validation error: {e}", file=sys.stderr)
                return 1
            print(json.dumps({"name": args.name, "valid": True}))
            return 0

        if args.estimate:
            out = {"name": args.name, **estimate_cost(body)}
            print(json.dumps(out, indent=2))
            return 0

        if args.dry_run:
            preview = build_text_episode_preview(
                name=args.name, body=body, group_id=group_id
            )
            preview["dry_run"] = True
            print(json.dumps(preview, indent=2))
            return 0

        asyncio.run(
            ingest_text_episode(name=args.name, body=body, group_id=group_id)
        )
        return 0

    # --- Session-dir path --------------------------------------------------
    if not args.target:
        print(
            "error: target is required (pass a session dir, 'latest', or --episode-text)",
            file=sys.stderr,
        )
        return 2

    try:
        path = resolve_target(args.target)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not path.exists() or not path.is_dir():
        print(f"error: not a directory: {path}", file=sys.stderr)
        return 2

    try:
        parse_session_dir(path)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not is_ingestable(path):
        print(
            f"error: {path.name} has no DISCOVERY.md or PLAN.md — skipping "
            "(bare SESSION.md yields low-signal extraction).",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        preview = build_episode_preview(path)
        preview["dry_run"] = True
        print(json.dumps(preview, indent=2))
        return 0

    if args.estimate:
        body = read_session_files(path)
        out = {"path": str(path), **estimate_cost(body)}
        print(json.dumps(out, indent=2))
        return 0

    if args.validate_only:
        body = read_session_files(path)
        errors = validate_body(body)
        if errors:
            for e in errors:
                print(f"validation error: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"path": str(path), "valid": True}))
        return 0

    # Real ingest — requires graphiti + LLM key
    asyncio.run(ingest_session(path, group_id=group_id_for(args.group)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
