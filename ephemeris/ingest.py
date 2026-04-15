"""ingest.py — Wiki ingestion pipeline for ephemeris.

Processes staged JSONL transcripts and writes structured knowledge to
the wiki directory. Implements the discover → schema → prompt → model
→ parse → write → cleanup pipeline.

Public API:
    PageResult       — dataclass(success, session_id, pages_written, error)
    IngestResult     — dataclass(results: list[PageResult])
    IngestSummary    — dataclass for CLI summary rendering
    ingest_one(transcript_path, wiki_root, model, log, session_id, session_date) -> PageResult
    ingest_all(staging_root, wiki_root, model, log) -> IngestResult
    list_pending_sessions(staging_root) -> list[Path]
    render_ingest_summary(summary: IngestSummary) -> str
    main(args: list[str] | None) -> None

CLI entry:
    python -m ephemeris.ingest                    # process all pending transcripts
    python -m ephemeris.ingest <session-id>       # process one specific session
    python -m ephemeris.ingest --dry-run          # parse + plan without writing

Environment overrides:
    EPHEMERIS_STAGING_ROOT  — staging root (default: ~/.claude/ephemeris/staging)
    EPHEMERIS_WIKI_ROOT     — wiki root (default: ~/.claude/ephemeris/wiki)
    EPHEMERIS_LOG_PATH      — diagnostic log (default: ~/.claude/ephemeris/ephemeris.log)
    EPHEMERIS_MODEL_CLIENT  — 'anthropic' or 'fake' (default: 'anthropic')
    EPHEMERIS_SCHEMA_PATH   — override schema file path; takes precedence over
                              ~/.claude/ephemeris/schema.md and wiki_root/SCHEMA.md
    ANTHROPIC_API_KEY       — required for AnthropicModelClient
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ephemeris.log import IngestLogger
    from ephemeris.model import ModelClient


@dataclass
class PageResult:
    """Result of processing a single transcript.

    Attributes:
        success: True if the transcript was fully processed without error.
        session_id: The session identifier.
        pages_written: Complete list of paths written or updated this run
            (union of pages_created and pages_updated). Maintained for
            backward compatibility with SPEC-003/SPEC-004 callers and the
            complete-log entry. Invariant:
            ``len(pages_written) == len(pages_created) + len(pages_updated)``
        pages_created: Subset of pages_written that were brand-new (did not
            exist before this run). Mutually exclusive with pages_updated.
        pages_updated: Subset of pages_written that merged into an existing
            page. Mutually exclusive with pages_created.
        contradictions: Count of conflict blocks injected across all page
            operations in this session.
        error: Error message if success is False; otherwise empty string.
    """

    success: bool
    session_id: str
    pages_written: list[Path] = field(default_factory=list)
    pages_created: list[Path] = field(default_factory=list)
    pages_updated: list[Path] = field(default_factory=list)
    contradictions: int = 0
    error: str = ""


@dataclass
class IngestResult:
    """Result of a bulk ingestion run.

    Attributes:
        results: One PageResult per processed transcript.
    """

    results: list[PageResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)


@dataclass
class IngestSummary:
    """Aggregated summary of a CLI ingest run.

    Used by render_ingest_summary() to produce the structured summary block
    printed at the end of every CLI invocation.

    Attributes:
        sessions_processed: Total sessions attempted (success + failure).
        pages_created: Count of brand-new wiki pages written.
        pages_updated: Count of existing pages that were updated.
        contradictions: Count of conflict blocks injected across all sessions.
        errors: Count of sessions that failed.
        error_lines: Human-readable error lines for each failed session.
    """

    sessions_processed: int
    pages_created: int
    pages_updated: int
    contradictions: int
    errors: int
    error_lines: list[str] = field(default_factory=list)


def render_ingest_summary(summary: IngestSummary) -> str:
    """Render a structured summary block from an IngestSummary.

    Pure function — no I/O or side effects.

    Args:
        summary: Populated IngestSummary dataclass.

    Returns:
        Multi-line string with the summary block, ending in a newline.
    """
    lines = [
        "=== Ingest Summary ===",
        f"Sessions processed: {summary.sessions_processed}",
        f"Pages created:      {summary.pages_created}",
        f"Pages updated:      {summary.pages_updated}",
        f"Contradictions:     {summary.contradictions}",
        f"Errors:             {summary.errors}",
    ]
    for error_line in summary.error_lines:
        lines.append(f"  ERROR: {error_line}")
    return "\n".join(lines) + "\n"


def list_pending_sessions(staging_root: Path) -> list[Path]:
    """Return all pending (unprocessed) JSONL transcript paths under staging_root.

    A pending transcript is any ``*.jsonl`` file found recursively under
    staging_root. Files are returned sorted alphabetically by path for
    deterministic ordering across runs.

    Args:
        staging_root: Root of the staging directory tree.

    Returns:
        Sorted list of Path objects pointing to JSONL transcript files.
    """
    return sorted(staging_root.rglob("*.jsonl"))


def ingest_one(
    transcript_path: Path,
    wiki_root: Path,
    model: "ModelClient",
    log: "IngestLogger",
    session_id: str,
    session_date: str,
    dry_run: bool = False,
    schema_text: Optional[str] = None,
) -> PageResult:
    """Process a single staged transcript through the ingestion pipeline.

    Pipeline stages:
    1. Parse JSONL transcript → plain text
    2. Bootstrap wiki schema if absent
    3. Build system + user prompts
    4. Invoke model
    5. Parse model response → PageOperation list
    6. Write wiki pages (unless dry_run)
    7. Delete staging file on success; write .error marker on failure

    Args:
        transcript_path: Path to the JSONL transcript file.
        wiki_root: Wiki root directory.
        model: Model client to invoke.
        log: Diagnostic logger.
        session_id: Session identifier (used in citations and log entries).
        session_date: Session date in YYYY-MM-DD format.
        dry_run: If True, skip all file writes and staging cleanup.
        schema_text: Pre-resolved schema string to embed in the ingestion prompt.
            When provided, skips the file-based schema resolution step.
            Callers should resolve once per run and pass the result here.
            If None, falls back to the existing wiki_root/SCHEMA.md lookup.

    Returns:
        PageResult with success=True and pages written, or success=False
        with an error message.
    """
    from ephemeris.exceptions import ParseResponseError
    from ephemeris.log import IngestLogger
    from ephemeris.merge import apply_merge_additions, inject_conflict_blocks, resolve_conflict_block
    from ephemeris.prompts import build_system_prompt, build_user_prompt, parse_response
    from ephemeris.schema import bootstrap_schema
    from ephemeris.stage import StageWriter
    from ephemeris.transcript import load_transcript, transcript_to_text
    from ephemeris.wiki import (
        _atomic_write_text,
        add_cross_references,
        build_new_page_content,
        write_page,
        _load_page,
    )

    # Recover any orphan journals from prior crashed runs before starting new work
    StageWriter.recover_orphans(wiki_root, log)

    start_ts = time.monotonic()
    citation = f"> Source: [{session_date} {session_id}]"

    # --- Stage 1: Parse transcript ---
    log.log(session_id, "parse", "ok", f"Loading transcript: {transcript_path}")
    try:
        load_result = load_transcript(transcript_path)
    except Exception as exc:
        elapsed = int((time.monotonic() - start_ts) * 1000)
        log.log(session_id, "parse", "error", f"Transcript parse failed: {exc}", elapsed)
        _write_error_marker(transcript_path, str(exc), dry_run)
        return PageResult(success=False, session_id=session_id, error=str(exc))

    if load_result.skipped_lines > 0:
        log.log(
            session_id,
            "parse",
            "warning",
            f"skipped {load_result.skipped_lines} malformed line(s) in transcript",
        )
    transcript_text = transcript_to_text(load_result.messages)

    # --- Stage 2: Bootstrap schema + resolve active schema ---
    log.log(session_id, "schema", "ok", "Bootstrapping wiki schema")
    if not dry_run:
        bootstrap_schema(wiki_root)
    if schema_text is None:
        # No pre-resolved schema — fall back to wiki-local lookup
        schema_path = wiki_root / "SCHEMA.md"
        schema_text = (
            schema_path.read_text(encoding="utf-8")
            if schema_path.exists()
            else ""
        )

    # --- Stage 3: Build prompts ---
    log.log(session_id, "prompt", "ok", "Building ingestion prompt")
    system_prompt = build_system_prompt(schema_text)
    user_prompt = build_user_prompt(transcript_text, session_id, session_date)

    # --- Stage 4: Invoke model ---
    log.log(session_id, "model", "ok", "Invoking model")
    model_start = time.monotonic()
    try:
        raw_response = model.invoke(system_prompt, user_prompt)
    except Exception as exc:
        elapsed = int((time.monotonic() - start_ts) * 1000)
        log.log(session_id, "model", "error", f"Model invocation failed: {exc}", elapsed)
        _write_error_marker(transcript_path, str(exc), dry_run)
        return PageResult(success=False, session_id=session_id, error=str(exc))
    model_elapsed = int((time.monotonic() - model_start) * 1000)
    log.log(session_id, "model", "ok", "Model response received", model_elapsed)

    # --- Stage 5: Parse response ---
    log.log(session_id, "parse_response", "ok", "Parsing model response")
    try:
        operations = parse_response(raw_response)
    except ParseResponseError as exc:
        elapsed = int((time.monotonic() - start_ts) * 1000)
        log.log(session_id, "parse_response", "error", f"Parse failed: {exc}", elapsed)
        _write_error_marker(transcript_path, str(exc), dry_run)
        return PageResult(success=False, session_id=session_id, error=str(exc))

    if not operations:
        # No extractable knowledge — still a success
        log.log(session_id, "write", "ok", "No operations extracted; nothing to write")
        _cleanup_staging(transcript_path, dry_run)
        elapsed = int((time.monotonic() - start_ts) * 1000)
        log.log(
            session_id,
            "complete",
            "ok",
            "Ingestion complete (no operations)",
            elapsed,
            pages_written=[],
        )
        return PageResult(success=True, session_id=session_id)

    # --- Stage 6: Write wiki pages ---
    if dry_run:
        log.log(session_id, "write", "ok", f"dry-run: would write {len(operations)} page(s)")
        return PageResult(success=True, session_id=session_id)

    pages_written: list[Path] = []
    pages_created: list[Path] = []
    pages_updated: list[Path] = []
    contradictions_count: int = 0
    # Build page_type_map for cross-reference resolution
    page_type_map: dict[str, str] = {op.page_name: op.page_type for op in operations}

    # --- Collect all merged content in-memory, then commit via StageWriter ---
    # This satisfies AC-1.1: all writes land atomically with journal-based rollback.
    pending_writes: list[tuple[Path, str]] = []  # (path, content)

    for op in operations:
        log.log(session_id, "write", "ok", f"Writing {op.page_type} page: {op.page_name!r}")
        try:
            from ephemeris.exceptions import WikiWriteError

            # --- SPEC-004 Slice 2 & 3: Merge with existing page if present ---
            existing_content = _load_page(op, wiki_root)
            if existing_content is not None and op.page_type in ("topic", "entity"):
                new_content_str = _op_new_content_str(op)

                # Call merge_topic — returns MergeResult (Slice 2)
                log.log(session_id, "merge", "ok", f"Merging into existing page: {op.page_name!r}")
                try:
                    merge_result = model.merge_topic(existing_content, new_content_str, session_id)
                except Exception as merge_exc:
                    elapsed = int((time.monotonic() - start_ts) * 1000)
                    log.log(session_id, "merge", "error",
                            f"merge_topic failed for {op.page_name!r}: {merge_exc}", elapsed)
                    _write_error_marker(transcript_path, str(merge_exc), dry_run)
                    return PageResult(
                        success=False,
                        session_id=session_id,
                        pages_written=pages_written,
                        pages_created=pages_created,
                        pages_updated=pages_updated,
                        contradictions=contradictions_count,
                        error=str(merge_exc),
                    )

                # Apply net-new additions (AC-2.3)
                merged = apply_merge_additions(existing_content, merge_result.additions)

                # Detect + inject conflict blocks (Slice 3 AC-3.1)
                try:
                    if merge_result.conflicts:
                        log.log(session_id, "detect", "ok",
                                f"Conflicts detected in {op.page_name!r}: {len(merge_result.conflicts)}")
                        merged = inject_conflict_blocks(merged, merge_result.conflicts)
                        contradictions_count += len(merge_result.conflicts)
                    else:
                        log.log(session_id, "detect", "ok", f"No conflicts in {op.page_name!r}")

                    # Resolve existing conflict block if affirmed (AC-3.4)
                    if merge_result.affirmed_claim:
                        merged = resolve_conflict_block(merged, merge_result.affirmed_claim)
                except Exception as detect_exc:
                    elapsed = int((time.monotonic() - start_ts) * 1000)
                    log.log(session_id, "detect", "error",
                            f"detect/inject failed for {op.page_name!r}: {detect_exc}", elapsed)
                    _write_error_marker(transcript_path, str(detect_exc), dry_run)
                    return PageResult(
                        success=False,
                        session_id=session_id,
                        pages_written=pages_written,
                        pages_created=pages_created,
                        pages_updated=pages_updated,
                        contradictions=contradictions_count,
                        error=str(detect_exc),
                    )

                # Append citation
                if "## Sessions" in merged:
                    merged = merged.rstrip() + f"\n{citation}\n"
                else:
                    merged = merged.rstrip() + f"\n\n## Sessions\n{citation}\n"

                page_path = _page_path_for_op(op, wiki_root)
                pending_writes.append((page_path, merged))
                pages_written.append(page_path)
                pages_updated.append(page_path)  # merged into existing page
            else:
                # New topic/entity page or decision (AC-2.4)
                log.log(session_id, "merge", "ok", f"No existing page; creating: {op.page_name!r}")
                log.log(session_id, "detect", "ok", f"New page, no conflict check: {op.page_name!r}")
                if op.page_type in ("topic", "entity"):
                    # Route through StageWriter for transactional protection
                    page_path, new_content = build_new_page_content(op, wiki_root, citation)
                    pending_writes.append((page_path, new_content))
                    pages_written.append(page_path)
                    pages_created.append(page_path)  # brand-new page
                else:
                    # Decision pages: always append-only, no pre-run state to protect
                    page_path = write_page(op, wiki_root, citation)
                    pages_written.append(page_path)
                    pages_created.append(page_path)  # brand-new decision page
        except Exception as exc:
            elapsed = int((time.monotonic() - start_ts) * 1000)
            log.log(session_id, "write", "error", f"Failed to write {op.page_name!r}: {exc}", elapsed)
            # Failure on any page write aborts the whole run
            _write_error_marker(transcript_path, str(exc), dry_run)
            return PageResult(
                success=False,
                session_id=session_id,
                pages_written=pages_written,
                pages_created=pages_created,
                pages_updated=pages_updated,
                contradictions=contradictions_count,
                error=str(exc),
            )

    # Commit all topic/entity writes transactionally via StageWriter (AC-1.1)
    if pending_writes:
        try:
            with StageWriter(wiki_root, log) as stage:
                for page_path, content in pending_writes:
                    stage.stage_write(page_path, content)
        except Exception as exc:
            elapsed = int((time.monotonic() - start_ts) * 1000)
            log.log(session_id, "write", "error",
                    f"Transactional write failed, rolled back: {exc}", elapsed)
            _write_error_marker(transcript_path, str(exc), dry_run)
            return PageResult(
                success=False,
                session_id=session_id,
                pages_written=[],
                pages_created=[],
                pages_updated=[],
                contradictions=contradictions_count,
                error=str(exc),
            )

    # --- Cross-reference pass ---
    for op, page_path in zip(operations, pages_written):
        if op.cross_references and op.page_type != "decision":
            add_cross_references(wiki_root, page_path, op.cross_references, page_type_map)

    # --- Stage 7: Cleanup staging ---
    log.log(session_id, "cleanup", "ok", "Removing staged transcript")
    _cleanup_staging(transcript_path, dry_run)

    elapsed = int((time.monotonic() - start_ts) * 1000)
    relative_pages = [
        str(p.relative_to(wiki_root)) for p in pages_written
    ]
    log.log(
        session_id,
        "complete",
        "ok",
        f"Ingestion complete: {len(pages_written)} page(s) written",
        elapsed,
        pages_written=relative_pages,
    )
    return PageResult(
        success=True,
        session_id=session_id,
        pages_written=pages_written,
        pages_created=pages_created,
        pages_updated=pages_updated,
        contradictions=contradictions_count,
    )


def ingest_all(
    staging_root: Path,
    wiki_root: Path,
    model: "ModelClient",
    log: "IngestLogger",
    dry_run: bool = False,
) -> IngestResult:
    """Process all pending transcripts in the staging root.

    Scans all ``<staging_root>/<hook_type>/<session_id>.jsonl`` files.
    Each transcript is processed independently — failure of one does not
    prevent processing of others.

    Args:
        staging_root: Root of the staging directory tree.
        wiki_root: Wiki root directory.
        model: Model client to invoke.
        log: Diagnostic logger.
        dry_run: If True, no files are written or deleted.

    Returns:
        IngestResult aggregating all PageResults.
    """
    import datetime

    from ephemeris.schema import resolve_schema

    result = IngestResult()

    # Find all *.jsonl files under staging_root (skip *.error files)
    transcript_paths = sorted(staging_root.rglob("*.jsonl"))

    if not transcript_paths:
        log.log("batch", "complete", "ok", "No pending transcripts found")
        return result

    today = datetime.date.today().isoformat()

    # Resolve schema once for the entire batch run (AC-9)
    # AC-2: auto-discover the well-known user schema path without requiring
    # EPHEMERIS_SCHEMA_PATH to be set.
    _user_schema_path = Path.home() / ".claude" / "ephemeris" / "schema.md"
    resolved_schema = resolve_schema(wiki_root, user_schema_path=_user_schema_path)

    for transcript_path in transcript_paths:
        session_id = transcript_path.stem
        page_result = ingest_one(
            transcript_path=transcript_path,
            wiki_root=wiki_root,
            model=model,
            log=log,
            session_id=session_id,
            session_date=today,
            dry_run=dry_run,
            schema_text=resolved_schema,
        )
        result.results.append(page_result)

    return result


def _op_new_content_str(op: "PageOperation") -> str:  # type: ignore[name-defined]  # noqa: F821
    """Extract a plain-text summary of new content from a PageOperation.

    Used as the ``new`` argument to ``model.merge_topic`` so the model can
    compare it against existing page content.
    """
    parts: list[str] = []
    if op.page_type == "topic":
        if op.content.get("overview"):
            parts.append(op.content["overview"])
        if op.content.get("details"):
            parts.append(op.content["details"])
    elif op.page_type == "entity":
        if op.content.get("role"):
            parts.append(op.content["role"])
    return "\n".join(parts)


def _page_path_for_op(op: "PageOperation", wiki_root: Path) -> Path:  # type: ignore[name-defined]  # noqa: F821
    """Return the target wiki file path for a topic or entity operation.

    Raises:
        ValueError: If op.page_type is not 'topic' or 'entity'.
    """
    from ephemeris.wiki import _sanitize_page_name

    safe_name = _sanitize_page_name(op.page_name)
    if op.page_type == "topic":
        return wiki_root / "topics" / f"{safe_name}.md"
    elif op.page_type == "entity":
        return wiki_root / "entities" / f"{safe_name}.md"
    raise ValueError(f"Unsupported page_type for path resolution: {op.page_type!r}")


def _cleanup_staging(transcript_path: Path, dry_run: bool) -> None:
    """Delete the staging file on success (per D8)."""
    if dry_run:
        return
    try:
        transcript_path.unlink(missing_ok=True)
    except OSError:
        pass


def _write_error_marker(
    transcript_path: Path,
    error_message: str,
    dry_run: bool,
) -> None:
    """Write a .error sibling file for failed transcripts (per D8)."""
    if dry_run:
        return
    import datetime

    error_path = transcript_path.with_suffix(".error")
    try:
        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        error_path.write_text(
            f"{timestamp}\n{error_message}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def main(argv: "list[str] | None" = None) -> None:
    """CLI entry point for ephemeris.ingest.

    Processes all pending transcripts or a single targeted session, prints
    per-session progress lines (AC-2) and a structured summary block (AC-1),
    and exits non-zero if any session fails (AC-6).

    Args:
        argv: Argument list (default: sys.argv[1:]). Passed directly to
              argparse so tests can call main() without subprocess overhead.
    """
    import argparse
    import datetime
    import sys

    def _resolve_env(var: str, default: str) -> Path:
        val = os.environ.get(var, default)
        return Path(val).expanduser()

    parser = argparse.ArgumentParser(
        description="ephemeris wiki ingestion engine",
        prog="python -m ephemeris.ingest",
    )
    parser.add_argument(
        "session_id",
        nargs="?",
        help="Process a specific session ID only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and plan without writing any files",
    )
    args = parser.parse_args(argv)

    # --- Validate session_id before any filesystem operations (MINOR-2) ---
    # Mirrors the _sanitize_page_name defense from SPEC-002 for user-controlled inputs.
    if args.session_id is not None:
        sid = args.session_id
        _INVALID_SESSION_CHARS = frozenset("/\\\x00:")
        if not sid:
            print(
                "ephemeris.ingest: invalid session ID — must not be empty",
                file=sys.stderr,
            )
            sys.exit(1)
        if ".." in sid.split("/")[0] or ".." in sid:
            print(
                f"ephemeris.ingest: invalid session ID {sid!r} — path traversal not allowed",
                file=sys.stderr,
            )
            sys.exit(1)
        if any(c in sid for c in _INVALID_SESSION_CHARS):
            bad = next(c for c in sid if c in _INVALID_SESSION_CHARS)
            print(
                f"ephemeris.ingest: invalid session ID {sid!r} — unsafe character {bad!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        if Path(sid).is_absolute():
            print(
                f"ephemeris.ingest: invalid session ID {sid!r} — absolute paths not allowed",
                file=sys.stderr,
            )
            sys.exit(1)

    staging_root = _resolve_env(
        "EPHEMERIS_STAGING_ROOT", "~/.claude/ephemeris/staging"
    )
    wiki_root = _resolve_env("EPHEMERIS_WIKI_ROOT", "~/.claude/ephemeris/wiki")
    log_path = _resolve_env("EPHEMERIS_LOG_PATH", "~/.claude/ephemeris/ephemeris.log")
    model_client_type = os.environ.get("EPHEMERIS_MODEL_CLIENT", "anthropic")

    from ephemeris.log import IngestLogger

    logger = IngestLogger(log_path)

    # Build model client
    if model_client_type == "fake":
        from ephemeris.model import FakeModelClient

        model: "ModelClient" = FakeModelClient()
    else:
        try:
            from ephemeris.model import AnthropicModelClient

            model = AnthropicModelClient()
        except Exception as exc:
            logger.log("cli", "model", "error", f"Cannot create model client: {exc}")
            print(f"ephemeris.ingest: {exc}", file=sys.stderr)
            sys.exit(1)

    today = datetime.date.today().isoformat()

    if args.session_id:
        # --- Targeted single-session mode (AC-5) ---
        candidates = list(staging_root.rglob(f"{args.session_id}.jsonl"))
        if not candidates:
            print(
                f"ephemeris.ingest: no staged transcript found for session {args.session_id!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        transcript_path = candidates[0]

        print(f"[1/1] Ingesting session {args.session_id}...", flush=True)

        from ephemeris.schema import resolve_schema

        # AC-2: auto-discover user schema for single-session mode (mirrors batch path)
        _user_schema_path = Path.home() / ".claude" / "ephemeris" / "schema.md"
        _resolved_schema = resolve_schema(wiki_root, user_schema_path=_user_schema_path)

        result_one = ingest_one(
            transcript_path=transcript_path,
            wiki_root=wiki_root,
            model=model,
            log=logger,
            session_id=args.session_id,
            session_date=today,
            dry_run=args.dry_run,
            schema_text=_resolved_schema,
        )

        if result_one.success:
            summary = IngestSummary(
                sessions_processed=1,
                pages_created=len(result_one.pages_created),
                pages_updated=len(result_one.pages_updated),
                contradictions=result_one.contradictions,
                errors=0,
                error_lines=[],
            )
            print(render_ingest_summary(summary), end="")
        else:
            summary = IngestSummary(
                sessions_processed=1,
                pages_created=0,
                pages_updated=0,
                contradictions=0,
                errors=1,
                error_lines=[f"{args.session_id}: {result_one.error}"],
            )
            print(render_ingest_summary(summary), end="")
            print(
                f"ephemeris.ingest: failed — {result_one.error}", file=sys.stderr
            )
            sys.exit(1)

    else:
        # --- Batch mode: all pending sessions ---
        pending = list_pending_sessions(staging_root)

        if not pending:
            print("No pending sessions found.")
            summary = IngestSummary(
                sessions_processed=0,
                pages_created=0,
                pages_updated=0,
                contradictions=0,
                errors=0,
                error_lines=[],
            )
            print(render_ingest_summary(summary), end="")
            return

        total = len(pending)
        pages_created_total = 0
        pages_updated_total = 0
        contradictions_total = 0
        error_lines: list[str] = []

        from ephemeris.schema import resolve_schema

        # AC-2: auto-discover user schema once for the batch run
        _user_schema_path = Path.home() / ".claude" / "ephemeris" / "schema.md"
        _resolved_schema = resolve_schema(wiki_root, user_schema_path=_user_schema_path)

        for i, transcript_path in enumerate(pending, start=1):
            session_id = transcript_path.stem
            print(f"[{i}/{total}] Ingesting session {session_id}...", flush=True)
            result = ingest_one(
                transcript_path=transcript_path,
                wiki_root=wiki_root,
                model=model,
                log=logger,
                session_id=session_id,
                session_date=today,
                dry_run=args.dry_run,
                schema_text=_resolved_schema,
            )
            if result.success:
                pages_created_total += len(result.pages_created)
                pages_updated_total += len(result.pages_updated)
                contradictions_total += result.contradictions
            else:
                error_lines.append(f"{session_id}: {result.error}")

        errors_total = len(error_lines)
        summary = IngestSummary(
            sessions_processed=total,
            pages_created=pages_created_total,
            pages_updated=pages_updated_total,
            contradictions=contradictions_total,
            errors=errors_total,
            error_lines=error_lines,
        )
        print(render_ingest_summary(summary), end="")

        if errors_total > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
