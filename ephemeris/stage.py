"""stage.py — Transactional wiki writes with rollback on failure and crash recovery.

The StageWriter records the pre-run content of every page it touches in a
journal file on disk. If the run completes, the journal is deleted. If the run
raises, the journal is used to roll back any pages that were atomically
replaced before the failure. If the process is SIGKILLed mid-run, the next
startup detects the orphaned journal and restores the pre-run state before
starting the new ingest.

Per-file writes use _atomic_write_text so no partial file is ever observable.

Public API:
    StageWriter — context manager for all-or-nothing wiki writes
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ephemeris.log import IngestLogger

import ephemeris.wiki as _wiki_mod


def _atomic_write(path: Path, content: str) -> None:
    """Thin wrapper that always delegates through the module reference.

    This indirection lets tests monkeypatch ``ephemeris.wiki._atomic_write_text``
    and have StageWriter pick up the patched version at call time.
    """
    _wiki_mod._atomic_write_text(path, content)


@dataclass
class _PendingWrite:
    path: Path
    new_content: str
    old_content: str | None  # None if the page did not exist pre-run
    applied: bool = False    # True after os.replace lands


class StageWriter:
    """Context manager for all-or-nothing wiki writes.

    Records pre-run content of every staged page to a journal file before
    applying any writes. On success the journal is deleted. On failure any
    applied writes are rolled back from the journal.

    Usage::

        with StageWriter(wiki_root, logger) as stage:
            stage.stage_write(topic_path, merged_content)
            stage.stage_write(entity_path, entity_content)
        # Exiting without exception commits all writes.
        # Exiting with exception rolls back any write that already landed.

    Args:
        wiki_root: Root directory of the wiki. Journal files are written here.
        logger: IngestLogger for recovery log entries.
    """

    def __init__(self, wiki_root: Path, logger: "IngestLogger") -> None:
        self._wiki_root = wiki_root.resolve()
        self._logger = logger
        self._run_id = uuid.uuid4().hex[:12]
        self._journal_path = self._wiki_root / f".ephemeris-journal-{self._run_id}.json"
        self._pending: list[_PendingWrite] = []
        self._entered = False

    def __enter__(self) -> "StageWriter":
        self._entered = True
        return self

    def stage_write(self, path: Path, new_content: str) -> None:
        """Queue a write.

        Reads the current content immediately so it is available for rollback
        even if the caller loses a reference to the original content.

        Args:
            path: Destination path for the new content.
            new_content: Content to write when committed.

        Raises:
            RuntimeError: If called outside a with-block.
        """
        if not self._entered:
            raise RuntimeError("stage_write called outside of with-block")
        old = path.read_text(encoding="utf-8") if path.exists() else None
        self._pending.append(
            _PendingWrite(path=path, new_content=new_content, old_content=old)
        )

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if not self._pending:
            return False
        if exc_type is not None:
            # Caller is already failing; nothing has been applied yet (we apply
            # in _commit), so there is nothing to roll back here.
            return False
        self._commit()
        return False

    def _commit(self) -> None:
        """Write journal then apply all pending writes atomically.

        Journal is written first as the durability boundary. If any page write
        raises, all previously-applied writes are rolled back from the journal
        and the journal is deleted before re-raising.
        """
        # 1. Write the journal to disk FIRST, before any os.replace.
        journal = {
            "run_id": self._run_id,
            "wiki_root": str(self._wiki_root),
            "entries": [
                {
                    "path": str(entry.path),
                    "old_content": entry.old_content,
                }
                for entry in self._pending
            ],
        }
        _atomic_write(self._journal_path, json.dumps(journal, indent=2))

        # 2. Apply each pending write atomically.
        try:
            for entry in self._pending:
                _atomic_write(entry.path, entry.new_content)
                entry.applied = True
        except Exception:
            self._rollback()
            raise

        # 3. Success: delete journal.
        self._journal_path.unlink(missing_ok=True)

    def _rollback(self) -> None:
        """Restore all applied writes to their pre-run state and delete the journal."""
        for entry in self._pending:
            if not entry.applied:
                continue
            if entry.old_content is None:
                # Page was new; delete it.
                entry.path.unlink(missing_ok=True)
            else:
                _atomic_write(entry.path, entry.old_content)
        self._journal_path.unlink(missing_ok=True)

    @classmethod
    def recover_orphans(cls, wiki_root: Path, logger: "IngestLogger") -> int:
        """Scan wiki_root for orphan journals from prior crashed runs and restore state.

        Called at ingest startup before any new work begins. Reads each orphan
        journal and restores every page to its pre-run content (or deletes
        newly-created pages). Logs each recovery.

        Args:
            wiki_root: Root directory of the wiki to scan.
            logger: IngestLogger for recovery log entries.

        Returns:
            Number of journals recovered (0 if none found).
        """
        wiki_root = wiki_root.resolve()
        count = 0
        for journal_path in sorted(wiki_root.glob(".ephemeris-journal-*.json")):
            try:
                data = json.loads(journal_path.read_text(encoding="utf-8"))
                for entry in data.get("entries", []):
                    page_path = Path(entry["path"])
                    old = entry.get("old_content")
                    if old is None:
                        page_path.unlink(missing_ok=True)
                    else:
                        _atomic_write(page_path, old)
                journal_path.unlink()
                logger.log(
                    session_id="recovery",
                    phase="recover",
                    status="ok",
                    message=f"recovered orphan journal {journal_path.name}",
                )
                count += 1
            except Exception as exc:
                logger.log(
                    session_id="recovery",
                    phase="recover",
                    status="error",
                    message=f"failed to recover {journal_path.name}: {exc}",
                )
        return count
