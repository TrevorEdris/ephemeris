#!/usr/bin/env python3
"""
update_session_index.py — Scan AI session directories and produce INDEX.md.

Usage:
    python update_session_index.py --sessions-root ~/src/.ai/sessions/
    python update_session_index.py --sessions-root ~/src/.ai/sessions/ --link "BOP-1074 blocks ENT-1750"
    python update_session_index.py --sessions-root ~/src/.ai/sessions/ --json

Exit codes:
    0 — Success
    1 — Error (invalid path, parse failure)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

# Matches session dir names like 2026-01-23_BOP-1000_CareFirst-Eligibility
# or 2026_01_21-ent-1240
SESSION_DIR_PATTERN = re.compile(
    r"^(\d{4})[_-](\d{2})[_-](\d{2})[_-](.+)$"
)

TICKET_PATTERN = re.compile(
    r"^([A-Z][\w]+-\d+)[_-](.+)$"
)

# Default keywords file path (relative to this script's directory)
DEFAULT_TOPICS_FILE = Path(__file__).parent.parent / "references" / "topic-keywords.txt"


def load_topic_keywords(topics_file: Path | None = None) -> list[str]:
    """Load topic keywords from a file. Falls back to built-in defaults."""
    path = topics_file or DEFAULT_TOPICS_FILE
    if path.exists():
        keywords = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                keywords.append(stripped.lower())
        return keywords
    # Fallback: generic development keywords if no file found
    return [
        "ci-cd", "config", "docker", "migration", "monitoring", "security",
        "terraform", "review", "claude", "mcp", "jira", "workflow",
        "airflow", "databricks", "oauth", "slack", "webhook", "playwright",
        "persona",
    ]


@dataclass
class SessionEntry:
    """A parsed session directory."""

    dir_name: str
    date: str
    ticket: str
    title: str
    has_discovery: bool = False
    has_plan: bool = False
    has_session: bool = False
    keywords: list[str] = field(default_factory=list)


@dataclass
class Dependency:
    """A relationship between two sessions."""

    from_ref: str
    relationship: str
    to_ref: str


VALID_RELATIONSHIPS = {"blocks", "blocked-by", "relates-to", "continues", "supersedes"}


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def parse_session_dir(dir_path: Path, topic_keywords: list[str]) -> SessionEntry | None:
    """Parse a session directory name into a SessionEntry."""
    name = dir_path.name
    match = SESSION_DIR_PATTERN.match(name)
    if not match:
        return None

    year, month, day, rest = match.groups()
    date = f"{year}-{month}-{day}"

    ticket = ""
    title = rest
    ticket_match = TICKET_PATTERN.match(rest)
    if ticket_match:
        ticket = ticket_match.group(1)
        title = ticket_match.group(2)

    # Normalize title for display
    title_display = title.replace("-", " ").replace("_", " ")

    # Extract topic keywords from the title slug
    title_lower = title.lower().replace("-", " ").replace("_", " ")
    keywords = [kw for kw in topic_keywords if kw in title_lower]

    entry = SessionEntry(
        dir_name=name,
        date=date,
        ticket=ticket,
        title=title_display,
        has_discovery=(dir_path / "DISCOVERY.md").exists(),
        has_plan=(dir_path / "PLAN.md").exists(),
        has_session=(dir_path / "SESSION.md").exists(),
        keywords=keywords,
    )
    return entry


def scan_sessions(root: Path, topic_keywords: list[str]) -> list[SessionEntry]:
    """Scan a sessions directory and return parsed entries."""
    entries = []
    if not root.is_dir():
        return entries

    for item in sorted(root.iterdir(), reverse=True):
        if not item.is_dir():
            continue
        entry = parse_session_dir(item, topic_keywords)
        if entry:
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Dependency management
# ---------------------------------------------------------------------------


def parse_existing_dependencies(index_path: Path) -> list[Dependency]:
    """Read existing dependencies from INDEX.md if it exists."""
    deps = []
    if not index_path.exists():
        return deps

    content = index_path.read_text(encoding="utf-8")
    in_deps = False
    for line in content.splitlines():
        if line.strip().startswith("## Dependencies"):
            in_deps = True
            continue
        if in_deps and line.strip().startswith("## "):
            break
        if in_deps and line.strip().startswith("|") and not line.strip().startswith("| From"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) == 3 and parts[0] != "---":
                deps.append(Dependency(from_ref=parts[0], relationship=parts[1], to_ref=parts[2]))
    return deps


def parse_link_arg(link_str: str) -> Dependency | None:
    """Parse a link argument like 'BOP-1074 blocks ENT-1750'."""
    parts = link_str.strip().split()
    if len(parts) != 3:
        return None
    from_ref, rel, to_ref = parts
    if rel not in VALID_RELATIONSHIPS:
        return None
    return Dependency(from_ref=from_ref, relationship=rel, to_ref=to_ref)


# ---------------------------------------------------------------------------
# Index generation
# ---------------------------------------------------------------------------


def generate_index(
    entries: list[SessionEntry],
    dependencies: list[Dependency],
) -> str:
    """Generate INDEX.md content."""
    from datetime import date

    lines = []
    lines.append("# Session Index")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")

    # Sessions table
    lines.append("## Sessions")
    lines.append("")
    lines.append("| Date | Ticket | Title | Discovery | Plan | Session |")
    lines.append("|------|--------|-------|-----------|------|---------|")
    for e in entries:
        d = "Y" if e.has_discovery else ""
        p = "Y" if e.has_plan else ""
        s = "Y" if e.has_session else ""
        lines.append(f"| {e.date} | {e.ticket} | {e.title} | {d} | {p} | {s} |")
    lines.append("")

    # Dependencies
    if dependencies:
        lines.append("## Dependencies")
        lines.append("")
        lines.append("| From | Relationship | To |")
        lines.append("|------|-------------|-----|")
        for dep in dependencies:
            lines.append(f"| {dep.from_ref} | {dep.relationship} | {dep.to_ref} |")
        lines.append("")

    # By topic (keyword extraction)
    topic_map: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        for kw in e.keywords:
            topic_map[kw].append(e.dir_name)

    if topic_map:
        lines.append("## By Topic")
        lines.append("")
        for topic in sorted(topic_map.keys()):
            dirs = topic_map[topic]
            if len(dirs) >= 2:  # Only show topics with 2+ sessions
                lines.append(f"### {topic}")
                for d in dirs:
                    lines.append(f"- {d}")
                lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Scan AI session directories and generate INDEX.md.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sessions-root",
        default=str(Path.home() / "src" / ".ai" / "sessions"),
        help="Path to the sessions directory (default: ~/src/.ai/sessions/)",
    )
    parser.add_argument(
        "--link",
        help='Record a dependency, e.g., "BOP-1074 blocks ENT-1750"',
    )
    parser.add_argument(
        "--topics-file",
        help="Path to a topic keywords file (one keyword per line). Default: references/topic-keywords.txt",
    )
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")
    args = parser.parse_args()

    root = Path(args.sessions_root).expanduser()
    if not root.is_dir():
        print(f"Error: sessions root not found: {root}", file=sys.stderr)
        return 1

    index_path = root / "INDEX.md"

    # Load topic keywords
    topics_file = Path(args.topics_file) if args.topics_file else None
    topic_keywords = load_topic_keywords(topics_file)

    # Scan sessions
    entries = scan_sessions(root, topic_keywords)

    # Load existing dependencies
    dependencies = parse_existing_dependencies(index_path)

    # Add new link if provided
    if args.link:
        new_dep = parse_link_arg(args.link)
        if new_dep is None:
            print(
                f"Error: invalid link format. Expected: '<FROM> <RELATIONSHIP> <TO>'\n"
                f"Valid relationships: {', '.join(sorted(VALID_RELATIONSHIPS))}",
                file=sys.stderr,
            )
            return 1
        # Avoid duplicates
        existing = {(d.from_ref, d.relationship, d.to_ref) for d in dependencies}
        if (new_dep.from_ref, new_dep.relationship, new_dep.to_ref) not in existing:
            dependencies.append(new_dep)

    # Generate index
    content = generate_index(entries, dependencies)
    index_path.write_text(content, encoding="utf-8")

    # Summary
    topic_count = len({kw for e in entries for kw in e.keywords})
    discovery_count = sum(1 for e in entries if e.has_discovery)
    plan_count = sum(1 for e in entries if e.has_plan)

    if args.json:
        summary = {
            "sessions": len(entries),
            "with_discovery": discovery_count,
            "with_plan": plan_count,
            "dependencies": len(dependencies),
            "topics": topic_count,
            "index_path": str(index_path),
        }
        print(json.dumps(summary, indent=2))
    else:
        print(f"Session index updated: {index_path}")
        print(f"  Sessions:     {len(entries)}")
        print(f"  w/ Discovery: {discovery_count}")
        print(f"  w/ Plan:      {plan_count}")
        print(f"  Dependencies: {len(dependencies)}")
        print(f"  Topics:       {topic_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
