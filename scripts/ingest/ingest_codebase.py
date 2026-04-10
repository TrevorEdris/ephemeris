#!/usr/bin/env python3
"""Ingest git merge commits + PR bodies into the codebase-history graph.

Strategy:
    Merge commits only — one per logical feature/fix. Merge commits carry
    the richest context (PR titles and bodies) and avoid noisy "wip"/"fmt"
    noise from the micro-commit timeline.

Deterministic paths (no Graphiti, no LLM):
    --dry-run         preview the episode list without calling add_episode
    --estimate        token + cost estimate per commit and total
    --validate-only   validate every episode body

Live path (requires graphiti-core + LLM key):
    python scripts/ingest/ingest_codebase.py --since "6 months ago"

Git fetch is isolated in ``fetch_merge_commits`` so tests can substitute a
fixture provider — the pure parsing / formatting / preview functions take
plain dicts and never touch subprocess.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from schema import CODEBASE_GROUP, EDGE_TYPES, ENTITY_TYPES_CODEBASE

# Same cost model used by ingest_sessions.py.
CHARS_PER_TOKEN = 4
MODEL_USD_PER_MTOK = 0.15

# Jira / Linear key pattern — uppercase project key + hyphen + integer.
TICKET_REF_PATTERN = re.compile(r"\b([A-Z]+-\d+)\b")

# Commit delimiter: "COMMIT::<sha>::<iso-timestamp>::<ref subject>".
# Split on "::" with maxsplit=3 so colons in the ISO timestamp are preserved.
_COMMIT_HEAD_PREFIX = "COMMIT::"


# --- Pure functions ---------------------------------------------------------


def parse_git_log_output(text: str) -> list[dict]:
    """Parse the custom ``--format`` output into commit dicts.

    Expected block shape::

        COMMIT::<sha>::<iso-date>::<merge ref subject>
        SUBJECT::<first non-merge subject>
        BODY::<body line 1>
        <body line 2>
        FILES::<file 1>
        <file 2>
        --COMMIT--

    ``SUBJECT`` is the commit's own subject line (usually the PR title);
    the head line's "ref subject" is the auto-generated merge message.
    """
    commits: list[dict] = []
    for raw_block in text.split("--COMMIT--"):
        block = raw_block.strip("\n")
        if not block.strip():
            continue
        lines = block.split("\n")
        if not lines[0].startswith(_COMMIT_HEAD_PREFIX):
            continue
        head_parts = lines[0][len(_COMMIT_HEAD_PREFIX):].split("::", 2)
        if len(head_parts) < 2:
            continue
        sha = head_parts[0]
        when = head_parts[1]
        subject = ""
        body_lines: list[str] = []
        file_lines: list[str] = []
        section: str | None = None
        for line in lines[1:]:
            if line.startswith("SUBJECT::"):
                section = "subject"
                subject = line[len("SUBJECT::"):]
            elif line.startswith("BODY::"):
                section = "body"
                rest = line[len("BODY::"):]
                if rest:
                    body_lines.append(rest)
            elif line.startswith("FILES::"):
                section = "files"
                rest = line[len("FILES::"):]
                if rest:
                    file_lines.append(rest)
            else:
                if section == "body":
                    body_lines.append(line)
                elif section == "files":
                    if line.strip():
                        file_lines.append(line)
        commits.append(
            {
                "sha": sha,
                "authored_at": when,
                "subject": subject,
                "body": "\n".join(body_lines).strip(),
                "files_changed": [f for f in file_lines if f.strip()],
            }
        )
    return commits


def extract_ticket_refs(text: str) -> list[str]:
    """Return deduped, sorted list of Jira-style ticket keys in ``text``."""
    if not text:
        return []
    return sorted(set(TICKET_REF_PATTERN.findall(text)))


def format_commit_episode(commit: dict, pr: dict | None = None) -> str:
    """Build the episode body fed to ``add_episode``.

    Shape:
        <subject>
        <body>                (if present)
        PR #<n>: <title>       (if pr)
        <pr.body[:2000]>       (if pr.body)
        Files changed: <first 20 comma-joined>
    """
    parts: list[str] = [commit["subject"]]
    if commit.get("body"):
        parts.append(commit["body"])
    if pr:
        parts.append(f"PR #{pr['number']}: {pr.get('title', '')}")
        pr_body = pr.get("body") or ""
        if pr_body:
            parts.append(pr_body[:2000])
    files = commit.get("files_changed", [])[:20]
    parts.append(f"Files changed: {', '.join(files)}")
    return "\n\n".join(parts)


def build_episode_preview(commit: dict, pr: dict | None = None) -> dict:
    body = format_commit_episode(commit, pr=pr)
    excerpt_len = 400
    return {
        "name": f"commit {commit['sha'][:7]}: {commit['subject']}",
        "group_id": CODEBASE_GROUP,
        "source_description": "git log + GitHub PR",
        "reference_time": commit["authored_at"],
        "sha": commit["sha"],
        "episode_body_bytes": len(body),
        "episode_body_excerpt": body[:excerpt_len],
    }


def estimate_cost(body: str) -> dict:
    tokens = max(1, len(body) // CHARS_PER_TOKEN)
    cost = (tokens / 1_000_000) * MODEL_USD_PER_MTOK
    return {"tokens": tokens, "cost_usd": round(cost, 6)}


def validate_body(body: str) -> list[str]:
    errors: list[str] = []
    if not body.strip():
        errors.append("empty body")
    if (len(body) // CHARS_PER_TOKEN) > 8000:
        errors.append("exceeds 8K token soft cap")
    return errors


# --- IO layer (git + GitHub) -----------------------------------------------


_GIT_LOG_FORMAT = (
    "COMMIT::%H::%aI::%s%n"
    "SUBJECT::%s%n"
    "BODY::%b%n"
)


def fetch_merge_commits(
    repo: Path,
    since: str | None = "6 months ago",
    paths: list[str] | None = None,
    all_history: bool = False,
) -> list[dict]:
    """Run ``git log --merges`` and return parsed commit dicts.

    Each commit block is followed by ``git show --name-only`` to collect the
    file list — ``git log`` cannot emit both ``%b`` and ``--name-only``
    cleanly in a single pass.
    """
    args = ["git", "-C", str(repo), "log", "--merges", f"--format={_GIT_LOG_FORMAT}"]
    if not all_history and since:
        args.append(f"--since={since}")
    if paths:
        args.append("--")
        args.extend(paths)
    proc = subprocess.run(args, capture_output=True, text=True, check=True)
    # git log alone cannot emit files_changed inline — paste synthetic FILES::
    # lines by calling git show for each sha afterward.
    partial = parse_git_log_output(proc.stdout + "--COMMIT--\n")
    for commit in partial:
        show = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "show",
                "--name-only",
                "--format=",
                commit["sha"],
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        commit["files_changed"] = [
            line for line in show.stdout.splitlines() if line.strip()
        ]
    return partial


def fetch_pr_for_commit(commit_sha: str, repo: Path) -> dict | None:
    """Optional PR lookup via ``gh pr list``. Silent failure → return None."""
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "merged",
                "--search",
                commit_sha,
                "--json",
                "number,title,body",
                "--limit",
                "1",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    data = json.loads(proc.stdout or "[]")
    return data[0] if data else None


async def ingest_codebase(
    commits: list[dict], *, repo: Path, skip_pr: bool = False
) -> None:
    """Live path — requires graphiti-core and LLM API key."""
    from graphiti_core.nodes import EpisodeType  # noqa: PLC0415

    from ingest.graphiti_client import get_graphiti  # noqa: PLC0415

    graphiti = await get_graphiti()
    for commit in commits:
        pr = None if skip_pr else fetch_pr_for_commit(commit["sha"], repo)
        body = format_commit_episode(commit, pr=pr)
        result = await graphiti.add_episode(
            name=f"commit {commit['sha'][:7]}: {commit['subject']}",
            episode_body=body,
            source_description="git log + GitHub PR",
            reference_time=datetime.fromisoformat(commit["authored_at"]),
            source=EpisodeType.text,
            group_id=CODEBASE_GROUP,
            entity_types=ENTITY_TYPES_CODEBASE,
            edge_types=EDGE_TYPES,
        )
        print(
            json.dumps(
                {
                    "sha": commit["sha"][:7],
                    "episode_uuid": str(result.episode.uuid),
                    "nodes_extracted": len(result.nodes),
                    "edges_extracted": len(result.edges),
                }
            )
        )


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Target git repo path")
    parser.add_argument(
        "--since", default="6 months ago", help="Git --since filter"
    )
    parser.add_argument(
        "--paths", nargs="*", default=None, help="Limit to these path globs"
    )
    parser.add_argument(
        "--all", action="store_true", help="Ignore --since; full history"
    )
    parser.add_argument("--no-pr", action="store_true", help="Skip gh PR lookup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    try:
        commits = fetch_merge_commits(
            repo=repo,
            since=None if args.all else args.since,
            paths=args.paths,
            all_history=args.all,
        )
    except subprocess.CalledProcessError as e:
        print(f"error: git log failed: {e.stderr}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: git not installed: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        previews = [build_episode_preview(c) for c in commits]
        print(json.dumps({"dry_run": True, "previews": previews}, indent=2))
        return 0

    if args.estimate:
        total_tokens = 0
        total_cost = 0.0
        per = []
        for c in commits:
            body = format_commit_episode(c)
            est = estimate_cost(body)
            total_tokens += est["tokens"]
            total_cost += est["cost_usd"]
            per.append({"sha": c["sha"][:7], **est})
        print(
            json.dumps(
                {
                    "commits": len(commits),
                    "estimated_tokens_total": total_tokens,
                    "estimated_cost_usd_total": round(total_cost, 6),
                    "model_assumed": "gpt-4o-mini",
                    "per_commit": per,
                },
                indent=2,
            )
        )
        return 0

    if args.validate_only:
        all_errors = []
        for c in commits:
            body = format_commit_episode(c)
            errs = validate_body(body)
            if errs:
                all_errors.append({"sha": c["sha"][:7], "errors": errs})
        if all_errors:
            print(
                json.dumps(
                    {"commits": len(commits), "valid": False, "errors": all_errors},
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        print(json.dumps({"commits": len(commits), "valid": True}))
        return 0

    asyncio.run(ingest_codebase(commits, repo=repo, skip_pr=args.no_pr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
