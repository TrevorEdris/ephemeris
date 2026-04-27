"""cli.py — thin command-line surface used by the /ephemeris:ingest slash command.

Subcommands:
    list-sources                          — print resolved sources from config.
    scan --source <id> [--ignore-cursor]  — list pending locators for one source.
    scan-path <path>                      — auto-detect a path's source kind and list locators.
    read --source <id> --identifier <id>  — print IngestUnit JSON for one locator.
    cite --page <p> --when <d> --kind <k> --identifier <i>
                                          — append citation if not already present.
    mark --source <id> --identifier <i> --mtime <epoch>
                                          — record cursor entry.
    bootstrap                             — write default config and default schema.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

from ephemeris.citations import append_citation
from ephemeris.config import (
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_PATH,
    EphemerisConfig,
    SourceSpec,
    load_config,
)
from ephemeris.cursor import Cursor
from ephemeris.sources.arbitrary_md import ArbitraryMarkdownSource
from ephemeris.sources.base import IngestUnit, Locator, Source
from ephemeris.sources.native_transcript import NativeTranscriptSource
from ephemeris.sources.session_docs import SessionDocsSource


def _print_unit_json(unit: IngestUnit) -> None:
    payload = {
        "kind": unit.locator.kind,
        "identifier": unit.locator.identifier,
        "when": unit.locator.when,
        "path": str(unit.locator.path),
        "raw_text": unit.raw_text,
        "structured_sections": unit.structured_sections,
        "metadata": unit.metadata,
        "source_mtime": unit.source_mtime,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _find_spec(config: EphemerisConfig, source_id: str) -> SourceSpec | None:
    for spec in config.sources:
        if spec.id == source_id:
            return spec
    return None


def _scan(spec: SourceSpec, cursor: Cursor, ignore_cursor: bool) -> list[tuple[Locator, float]]:
    items: list[tuple[Locator, float]] = []
    for locator in spec.source.scan(spec.root):
        try:
            mtime = locator.path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if not ignore_cursor and cursor.is_fresh(spec.id, locator, mtime):
            continue
        items.append((locator, mtime))
    items.sort(key=lambda item: (item[0].when, item[0].identifier))
    return items


def _detect_source_for_path(path: Path) -> tuple[Source, Path, str]:
    """Auto-detect a source / scan-root / synthetic id for a user-supplied path."""
    resolved = path.expanduser().resolve()
    if resolved.is_file() and resolved.suffix.lower() == ".jsonl":
        # Single transcript — synthesize a one-shot project root.
        src = NativeTranscriptSource(filter_title_gen=False)
        return src, resolved.parent, "native-claude-projects"
    if resolved.is_dir():
        # Heuristic: contains *.jsonl directly → native projects.
        if any(resolved.glob("*.jsonl")):
            src = NativeTranscriptSource(filter_title_gen=True)
            # Treat the parent as scan root if this dir looks like a project dir.
            return src, resolved.parent if any(p.is_dir() for p in resolved.iterdir()) is False else resolved, "native-claude-projects"
        # Heuristic: contains subdirs with *.md → session-docs.
        has_md_subdirs = any(
            p.is_dir() and any(p.glob("*.md")) for p in resolved.iterdir()
        )
        if has_md_subdirs:
            return SessionDocsSource(), resolved, "session-docs-adhoc"
        # Heuristic: leaf dir with *.md → single arbitrary-md unit.
        if any(resolved.glob("*.md")):
            return ArbitraryMarkdownSource(), resolved, "arbitrary-md-adhoc"
    if resolved.is_file() and resolved.suffix.lower() == ".md":
        return ArbitraryMarkdownSource(), resolved, "arbitrary-md-adhoc"
    # Fallback: arbitrary-md source with the path as-is.
    return ArbitraryMarkdownSource(), resolved, "arbitrary-md-adhoc"


def cmd_list_sources(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    for spec in config.sources:
        sys.stdout.write(f"{spec.id}\t{spec.kind}\t{spec.root}\n")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    spec = _find_spec(config, args.source)
    if spec is None:
        sys.stderr.write(f"unknown source: {args.source}\n")
        return 2
    cursor = Cursor.load(config.cursor_path)
    for locator, _mtime in _scan(spec, cursor, args.ignore_cursor):
        sys.stdout.write(
            f"{locator.kind}\t{locator.identifier}\t{locator.when}\t{locator.path}\n"
        )
    return 0


def cmd_scan_path(args: argparse.Namespace) -> int:
    path = Path(args.path)
    source, root, synth_id = _detect_source_for_path(path)
    sys.stdout.write(f"# source-id\t{synth_id}\n")
    sys.stdout.write(f"# kind\t{source.kind}\n")
    sys.stdout.write(f"# root\t{root}\n")
    for locator in source.scan(root):
        sys.stdout.write(
            f"{locator.kind}\t{locator.identifier}\t{locator.when}\t{locator.path}\n"
        )
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    spec = _find_spec(config, args.source)
    if spec is None:
        sys.stderr.write(f"unknown source: {args.source}\n")
        return 2
    target_id = args.identifier
    for locator in spec.source.scan(spec.root):
        if locator.identifier == target_id:
            unit = spec.source.read(locator)
            _print_unit_json(unit)
            return 0
    sys.stderr.write(f"identifier not found: {target_id}\n")
    return 1


def cmd_read_path(args: argparse.Namespace) -> int:
    path = Path(args.path)
    source, root, _ = _detect_source_for_path(path)
    target_id = args.identifier
    for locator in source.scan(root):
        if not target_id or locator.identifier == target_id:
            unit = source.read(locator)
            _print_unit_json(unit)
            return 0
    sys.stderr.write(f"no readable locator at {path}\n")
    return 1


def cmd_cite(args: argparse.Namespace) -> int:
    page = Path(args.page)
    if not page.exists():
        sys.stderr.write(f"page not found: {page}\n")
        return 1
    text = page.read_text(encoding="utf-8")
    new_text = append_citation(text, args.when, args.kind, args.identifier)
    if new_text != text:
        page.write_text(new_text, encoding="utf-8")
        sys.stdout.write("appended\n")
    else:
        sys.stdout.write("already-present\n")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    cursor = Cursor.load(config.cursor_path)
    locator = Locator(
        path=Path(args.path) if args.path else Path("/"),
        kind=args.kind or args.source,
        identifier=args.identifier,
        when=args.when or "",
    )
    cursor.update(args.source, locator, float(args.mtime), run_id=args.run_id or _new_run_id())
    cursor.save()
    sys.stdout.write("ok\n")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    cfg_path = DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
        sys.stdout.write(f"wrote {cfg_path}\n")
    else:
        sys.stdout.write(f"already exists: {cfg_path}\n")
    return 0


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ephemeris.cli")
    parser.add_argument(
        "--config",
        type=lambda s: Path(s).expanduser(),
        default=None,
        help="Override config path",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-sources").set_defaults(func=cmd_list_sources)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--source", required=True)
    p_scan.add_argument("--ignore-cursor", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_scan_path = sub.add_parser("scan-path")
    p_scan_path.add_argument("path")
    p_scan_path.set_defaults(func=cmd_scan_path)

    p_read = sub.add_parser("read")
    p_read.add_argument("--source", required=True)
    p_read.add_argument("--identifier", required=True)
    p_read.set_defaults(func=cmd_read)

    p_read_path = sub.add_parser("read-path")
    p_read_path.add_argument("path")
    p_read_path.add_argument("--identifier", default="")
    p_read_path.set_defaults(func=cmd_read_path)

    p_cite = sub.add_parser("cite")
    p_cite.add_argument("--page", required=True)
    p_cite.add_argument("--when", required=True)
    p_cite.add_argument("--kind", required=True)
    p_cite.add_argument("--identifier", required=True)
    p_cite.set_defaults(func=cmd_cite)

    p_mark = sub.add_parser("mark")
    p_mark.add_argument("--source", required=True)
    p_mark.add_argument("--identifier", required=True)
    p_mark.add_argument("--mtime", required=True)
    p_mark.add_argument("--path", default="")
    p_mark.add_argument("--kind", default="")
    p_mark.add_argument("--when", default="")
    p_mark.add_argument("--run-id", default="")
    p_mark.set_defaults(func=cmd_mark)

    sub.add_parser("bootstrap").set_defaults(func=cmd_bootstrap)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
