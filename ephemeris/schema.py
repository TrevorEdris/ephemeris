"""schema.py — ephemeris default wiki schema and bootstrap utilities.

Provides DEFAULT_SCHEMA, a string constant describing the three wiki page
types (topic, entity, decision log) and their naming conventions.

Public API:
    DEFAULT_SCHEMA: str  — the embedded default schema document
    bootstrap_schema(wiki_root: Path) -> None  — write SCHEMA.md if absent
    load_user_schema(path: Path) -> str | None  — read + validate a schema file
    resolve_schema(wiki_root: Path, user_schema_path: Path | None = None) -> str
        — resolve the active schema using the 4-level precedence chain
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_log = logging.getLogger("ephemeris.schema")

# Maximum schema file size: 64 KB
_MAX_SCHEMA_SIZE: int = 64 * 1024

DEFAULT_SCHEMA: str = """\
# Ephemeris Wiki Schema

This document defines the structure and conventions for all wiki pages
managed by the ephemeris ingestion engine. All generated pages must
conform to the conventions described here.

---

## Page Types

### Topic Pages

- **Directory:** `wiki/topics/`
- **Naming:** `kebab-case.md` (e.g., `error-handling-strategy.md`)
- **Required Sections:**
  - `## Overview` — concise summary of the topic (1-3 sentences)
  - `## Details` — extended discussion; each session may append a subsection
  - `## Sessions` — citation list; one line per contributing session

**Example:**

```markdown
# Error Handling Strategy

## Overview
All errors are wrapped in domain-specific exception types before propagation.

## Details

### 2026-04-15 (session-abc123)
The team decided to use a base `AppError` class with typed subclasses.
...

## Sessions
> Source: [2026-04-15 session-abc123]
```

---

### Entity Pages

- **Directory:** `wiki/entities/`
- **Naming:** `PascalCase.md` (e.g., `TranscriptCapture.md`)
- **Required Sections:**
  - `## Role` — what this component/system does in one paragraph
  - `## Relationships` — bulleted list of named relationships to other entities
  - `## Sessions` — citation list; one line per contributing session

**Example:**

```markdown
# TranscriptCapture

## Role
Captures raw session transcripts from Claude Code hooks and persists them
atomically to a staging directory keyed by session ID.

## Relationships
- [IngestEngine](IngestEngine.md) — consumes staged transcripts
- [HookPayload](HookPayload.md) — provides the source transcript path

## Sessions
> Source: [2026-04-15 session-abc123]
```

---

### Decision Log

- **File:** `wiki/DECISIONS.md` (single shared file, newest-first)
- **Entry format:** `## [YYYY-MM-DD] <title>`
  - `**Decision:**` — what was decided
  - `**Rationale:**` — why this decision was made
  - `**Session:**` — citation linking to the source session

**Example:**

```markdown
## [2026-04-15] Use atomic rename for staging writes

**Decision:** All staging writes use `os.replace()` after writing to a
temp file in the destination directory.

**Rationale:** Atomic rename guarantees readers never see partial data
and no orphaned temp files remain on crash.

**Session:** > Source: [2026-04-15 session-abc123]
```

---

## Cross-References

Use standard markdown links relative to the wiki root:

- From a topic page to an entity: `[EntityName](../entities/EntityName.md)`
- From an entity page to a topic: `[topic-name](../topics/topic-name.md)`
- From a decision to an entity: `[EntityName](entities/EntityName.md)`

---

## Citation Format

Every page must include a `## Sessions` section (or inline `**Session:**`
for decision entries) with citations in the following format:

```
> Source: [YYYY-MM-DD session-id]
```

Citations are appended by the ingestion engine; they are never generated
by the model.

---

## Naming Conventions

| Type | Convention | Examples |
|------|-----------|---------|
| Topic | `kebab-case` | `error-handling-strategy`, `api-design-patterns` |
| Entity | `PascalCase` | `TranscriptCapture`, `IngestEngine`, `ModelClient` |
| Decision | Date-prefixed title | `[2026-04-15] Use atomic rename` |

---

## Model Output Format

When the ingestion engine queries the model, it expects a JSON response
with the following structure:

```json
{
  "operations": [
    {
      "action": "create",
      "page_type": "topic",
      "page_name": "error-handling-strategy",
      "content": {
        "overview": "All errors are wrapped in domain-specific types.",
        "details": "The team decided to use a base AppError class..."
      },
      "cross_references": ["TranscriptCapture"]
    }
  ]
}
```

If the transcript contains no extractable knowledge, the model must return:
```json
{"operations": []}
```
"""


def load_user_schema(path: Path) -> str | None:
    """Read and validate a user-supplied schema file.

    Validation rules (any failure returns None silently):
    - File must exist
    - File size must be <= 64 KB
    - File must be valid UTF-8
    - File must be non-empty after decoding

    The caller (resolve_schema) is responsible for debug logging when None
    is returned for reasons other than absence.

    Args:
        path: Absolute path to the schema file.

    Returns:
        File content as a string, or None if the file is absent, empty,
        oversized, or undecodable.
    """
    if not path.exists():
        return None

    try:
        size = path.stat().st_size
    except OSError:
        return None

    if size > _MAX_SCHEMA_SIZE:
        return None  # Caller logs the reason

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # Caller logs the reason

    if not content.strip():
        return None

    return content


def resolve_schema(
    wiki_root: Path,
    user_schema_path: Path | None = None,
) -> str:
    """Resolve the active wiki schema using the 4-level precedence chain.

    Precedence (highest to lowest):
    1. ``EPHEMERIS_SCHEMA_PATH`` env var — if set, non-empty, ≤ 64 KB, valid UTF-8
    2. ``user_schema_path`` argument — if given, non-empty, ≤ 64 KB, valid UTF-8
    3. ``wiki_root/SCHEMA.md`` — existing wiki-local schema
    4. ``DEFAULT_SCHEMA`` constant — always-valid fallback

    Invalid cases (empty, binary, > 64 KB) are skipped silently for levels 3-4;
    levels 1-2 log a single debug message and fall through to the next level.

    Args:
        wiki_root: Root directory of the wiki. Used for level-3 lookup.
        user_schema_path: Optional explicit path to a user schema file
            (e.g., ``~/.claude/ephemeris/schema.md``). Used as level 2.

    Returns:
        Schema text to embed in the ingestion prompt. Never raises.
    """
    # Level 1: EPHEMERIS_SCHEMA_PATH env var
    env_path_str = os.environ.get("EPHEMERIS_SCHEMA_PATH", "")
    if env_path_str:
        env_path = Path(env_path_str).expanduser()
        if env_path.exists():
            size = _safe_size(env_path)
            if size is not None and size > _MAX_SCHEMA_SIZE:
                _log.debug(
                    "EPHEMERIS_SCHEMA_PATH %s skipped: size %d bytes exceeds 64 KB limit",
                    env_path,
                    size,
                )
            else:
                content = _safe_read(env_path)
                if content is None:
                    _log.debug(
                        "EPHEMERIS_SCHEMA_PATH %s skipped: could not decode as UTF-8",
                        env_path,
                    )
                elif content:
                    return content
                # empty → fall through silently

    # Level 2: explicit user_schema_path argument
    if user_schema_path is not None:
        path = user_schema_path.expanduser() if not user_schema_path.is_absolute() else user_schema_path
        if path.exists():
            size = _safe_size(path)
            if size is not None and size > _MAX_SCHEMA_SIZE:
                _log.debug(
                    "User schema %s skipped: size %d bytes exceeds 64 KB limit",
                    path,
                    size,
                )
            else:
                content = _safe_read(path)
                if content is None:
                    _log.debug(
                        "User schema %s skipped: could not decode as UTF-8",
                        path,
                    )
                elif content:
                    return content
                # empty → fall through silently

    # Level 3: wiki_root/SCHEMA.md
    wiki_schema = wiki_root / "SCHEMA.md"
    if wiki_schema.exists():
        try:
            content = wiki_schema.read_text(encoding="utf-8")
            if content.strip():
                return content
        except (UnicodeDecodeError, OSError):
            pass  # fall through to default

    # Level 4: embedded DEFAULT_SCHEMA
    return DEFAULT_SCHEMA


def _safe_size(path: Path) -> int | None:
    """Return file size in bytes, or None on OSError."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def _safe_read(path: Path) -> str | None:
    """Return UTF-8 file content, or None on decode/OS error."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def bootstrap_schema(wiki_root: Path) -> None:
    """Write the default SCHEMA.md to wiki_root if it does not already exist.

    Idempotent: if SCHEMA.md already exists, this function is a no-op.
    No network calls are made; the schema is embedded in the module.

    Args:
        wiki_root: Root directory of the wiki. Created if absent.
    """
    wiki_root.mkdir(parents=True, exist_ok=True)
    schema_path = wiki_root / "SCHEMA.md"
    if not schema_path.exists():
        schema_path.write_text(DEFAULT_SCHEMA, encoding="utf-8")
